# -*- coding: utf-8 -*-
"""真机用例执行器：按声明式 JSON 用例文件，在一台客户端上一次跑完并输出报告。

用法见 references/game-debugging.md「用例执行器」，设计见 specs/2026-11-05-case-runner.md。

    python -X utf8 case_runner.py run --root <项目> --devid <设备ID> <用例.json | spec.md> ...

- 不选设备、不加设备锁：由调用方（test 任务的主会话，或主线程直接回归时的 codex_cli.py lock）负责。
- 每次运行先 init_client 一次；每个用例自动开始报错收集、安装 Mock，执行步骤，
  最后在 finally 中等待延迟回调、逆序还原 Mock、核对监听、结束报错收集。
- 报告输出到 stdout，并保存到 <项目>/.mhxy-workspace/cases/reports/。退出码：0 通过，1 失败，2 受阻。

客户端代码约定同 execute_code：顶层定义的名字对函数不可见，最后一行的裸表达式是返回值。
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import tokenize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "exec-check"))
import mcp_http  # noqa: E402

ERROR_WATCH = HERE / "error_watch.py"
EXEC_TRACE = HERE.parent / "exec-check" / "exec_trace.py"
REPORT_DIR = Path(".mhxy-workspace") / "cases" / "reports"
TEMPLATE_DIR = HERE.parent.parent / "assets" / "cases"  # 用例模板，见 search
TEXT_LIMIT = 2000  # 报告中每个返回值、报错保留的字符数
STEP_TYPES = ("exec", "gm", "mcp", "wait_for", "assert", "exec_check", "war_act", "screenshot", "pump")
# 每种步骤除类型键外允许的选项
STEP_OPTIONS = {"exec": {"save_as"}, "gm": set(), "mcp": {"args", "save_as"}, "wait_for": set(),
                "assert": {"message"}, "exec_check": set(), "war_act": set(), "screenshot": set(), "pump": set()}
CASE_FIELDS = {"name", "mocks", "steps", "finally", "settle", "ignore_errors", "setup", "record", "frames", "clean_ui"}
# war_act 的动作：动作 → (必填字段, 默认目标)。默认目标 None 表示必须写 target；不需要目标的动作不在乎这一项。
# 与 WAR_HELPERS 中 _case_war_act 的发包分支一一对应，增删动作两处同步。
ROLE_ACTS = {"attack": ((), "e0"), "magic": (("id",), "e0"), "sp": (("id",), "e0"), "guard": ((), "self"),
             "protect": ((), None), "item": (("item",), "self"), "fabao": (("id",), "e0")}
PET_ACTS = {"attack": ((), "e0"), "magic": (("id",), "e0"), "guard": ((), "pet"), "protect": ((), None),
            "item": (("item",), "pet")}
# pump 的事件：op → (必填字段, 可选字段)。与 WAR_HELPERS 中 _case_pump 的构造分支一一对应，增删两处同步。
# 不提供 delete（会删掉真实战斗的单位）和 turn（war.turn() 会发包导致回合失步）
PUMP_OPS = {
    "perform": (("attacker_id", "victims", "magic_id"), ("magic_desc", "name", "info")),
    "attack": (("attacker_id", "victim_id"), ("series_attack",)),
    "wstate": (("victim_id",), ("hurt", "life", "ward", "hp_chg", "hp_ext", "magic_id")),
    "wstate_split": (("victim_id",), ("split_type",)),
    "status": (("victim_id", "status"), ("eff_status",)),
    "addon": (("wid", "pid"), ("turn", "level", "aid", "args")),
    "action_end": ((), ()),
}
PUMP_SHORTHAND = {"attacker", "magic_id", "victims", "hp_chg", "hits", "life", "status", "addons"}
VIDEO_WAIT = 30  # 停止录屏后等 mp4 写完的最长秒数
SHOT_WAIT = 10  # 截图异步写文件，等文件出现的最长秒数
FRAMES_NOTIFY = {"name": "帧采集导出弹窗", "patch": "frame_collector.g_collector._notify_export_done",
                 "value": "lambda *args, **kwargs: None"}  # frames: true 时内部安装，见 begin
SPEC_HEADING = re.compile(r"^(#+)\s*测试用例\s*$")
PLACEHOLDER = re.compile(r"\{(devid|root|(?:vars|args)\.[A-Za-z_]\w*)\}")

# wait_for 预设：领域 → 名字 → 客户端表达式（单个表达式，可用 {args.名字}）。
# 新玩法只在这里加预设，不改执行流程；每个预设都要在真机上验证过再加入。
PRESETS = {
    "war": {
        # utils3.is_in_war 即 event.IS_IN_WAR()，客户端各处判断是否在战斗中都用它
        "war_in": "__import__('utils3').is_in_war()",
        "war_out": "not __import__('utils3').is_in_war()",
        # 进入第 n 回合的等待下指令阶段。回合数用 ActualTurn（每回合 war.turn() 设置）；不能用 war.Turn：
        # 它是“已收到、未播完的回合协议”计数，进入回合时被 war.turn() 减 1，第 1 回合期间恒为 0（真机已验证）。
        # ActualTurn 只在 do_end() 重置、初值为 1，单独判断会在刚收到 S_WAR_START 或连续战斗时过早成立，所以叠加 WAR_WAITING
        "war_turn": "{waiting} and __import__('war').ActualTurn >= {{args.n}}",
        # 本场已进入某回合、表演播完、在等玩家下指令
        "war_idle": "{waiting}",
        # 帧采集器里 magic_id 相同、已播完（FRAME_ACTION_END 后归档进回合）的出手次数达到 n。需要用例 frames: true。
        # 战斗中看 _battle（已归档回合 + 当前回合），战斗结束后看 _last_battle；用例开始前就有的上一场
        # （_case_media_start 记在 sys._mhxy_case_frames_prev）不算，与 _case_media_finish 一致
        "war_action": ("(lambda c: sum(1 for t in ((c._battle.turns + ([c._cur_turn] if c._cur_turn else []))"
                       " if c._battle else (c._last_battle.turns if c._last_battle is not None and id(c._last_battle)"
                       " != getattr(__import__('sys'), '_mhxy_case_frames_prev', None) else []))"
                       " for a in t.actions if a.magic_id == {{args.magic_id}} and a.end_frame >= 0))"
                       "(__import__('frame_collector').get_instance()) >= {{args.n}}"),
    },
}
FRAME_PRESETS = {"war_action"}  # 依赖帧采集，用例必须 frames: true
# 本场战斗已执行过 war.turn()（war.start() 把 PlayerTurn 清零，war.turn() 加 1）、命令队列为空（连续战斗时
# 上一场的 war.end／本场 war.start 还在队列里，此条排除它们）、当前处理函数是 wait_cmd
WAR_WAITING = ("__import__('utils3').is_in_war() and __import__('war').PlayerTurn >= 1 and not __import__('war').Cmds"
               " and __import__('war').ProcessFunc == __import__('war').wait_cmd")
PRESETS["war"] = {name: expr.format(waiting=WAR_WAITING) for name, expr in PRESETS["war"].items()}
PRESET_INDEX = {name: expr for group in PRESETS.values() for name, expr in group.items()}

# 客户端辅助函数，与 error_watch.py 一起发送。每次 execute_code 往返约 3 秒，所以用例开始（报错收集、
# 监听基线、patch Mock 安装）和收尾（patch Mock 还原、监听核对、结束收集）各合并成一次调用。
# 各函数自包含（execute_code 中顶层名字对函数不可见），自己捕获异常并返回结果，同一次调用里一项失败不影响其他项。
# patch 备份登记在 sys._mhxy_case_mocks（{名字: (对象, 属性, 来源, 原值, 新值)}），跨多次调用仍在。来源决定还原方式：
# own（对象自己的 __dict__，写回原值）、inherited（类上继承，删除覆盖）、absent（原本没有，删除）、
# proxy（__getattr__ 代理，如 sdata.huodong：读取时才取值或缓存，写回原值）、
# descriptor（实例的类上有数据描述符，如 sdata 的 Property：赋值走 __set__，写回原值）。
CLIENT_HELPERS = '''def _case_install(name, target, value_src):
	import importlib
	import sys
	import traceback
	try:
		store = sys.__dict__.setdefault("_mhxy_case_mocks", {})
		if name in store:
			raise RuntimeError(f"Mock {name} 已有安装记录，可能是上次运行没有还原")
		parts = target.split(".")
		for i in range(len(parts) - 1, 0, -1):
			try:
				obj = importlib.import_module(".".join(parts[:i]))
				break
			except ImportError:
				continue
		else:
			raise ImportError(f"找不到 {target} 所在的模块")
		for part in parts[i:-1]:
			obj = getattr(obj, part)
		attr = parts[-1]
		own = vars(obj) if hasattr(obj, "__dict__") else {}
		bases = obj.__mro__[1:] if isinstance(obj, type) else type(obj).__mro__
		found = next((vars(base)[attr] for base in bases if attr in vars(base)), None)
		if attr in own:
			mode, old = "own", own[attr]
		elif not hasattr(obj, attr):  # 代理的 __getattr__ 可能在这里把值缓存进 __dict__（如 sdata），不影响下面的判断
			mode, old = "absent", None
		elif attr in own:
			mode, old = "proxy", own[attr]
		elif found is not None and not isinstance(obj, type) and hasattr(type(found), "__set__"):
			mode, old = "descriptor", getattr(obj, attr)  # 类上的数据描述符（如 sdata 的 Property）：赋值走 __set__，还原写回
		elif found is not None:
			mode, old = "inherited", None
		else:
			mode, old = "proxy", getattr(obj, attr)
		value = eval(value_src, {"orig": getattr(obj, attr, None)})
		store[name] = (obj, attr, mode, old, value)  # 先登记再替换：替换失败时还原也只是写回原值
		setattr(obj, attr, value)
		if mode in ("proxy", "descriptor") and getattr(obj, attr, None) is not value:
			raise RuntimeError(f"{target} 由代理或描述符提供，替换后读回的不是新值，改用 install/restore 型 Mock")
		return {"installed": True, "mode": mode}
	except Exception:
		return {"error": traceback.format_exc()[-2000:]}


def _case_restore(name):
	import sys
	import traceback
	try:
		store = sys.__dict__.get("_mhxy_case_mocks", {})
		if name not in store:
			return {"restored": False, "reason": "没有安装记录"}
		obj, attr, mode, old, value = store.pop(name)
		if not store:
			del sys._mhxy_case_mocks
		if mode == "own":
			setattr(obj, attr, old)
			return {"restored": vars(obj).get(attr) is old, "mode": mode}
		if mode in ("proxy", "descriptor"):
			setattr(obj, attr, old)
			return {"restored": getattr(obj, attr, None) is old, "mode": mode}
		if attr in (vars(obj) if hasattr(obj, "__dict__") else {}) or (mode == "absent" and hasattr(obj, attr)):
			delattr(obj, attr)
		if mode == "inherited":
			return {"restored": attr not in vars(obj), "mode": mode}
		return {"restored": not hasattr(obj, attr), "mode": mode}
	except Exception:
		return {"restored": False, "reason": traceback.format_exc()[-2000:]}


def _case_clean_ui():
	"""开局整理：按清单逐项关闭遮挡场景的窗口（清单与真机依据见 spec 0.3.31），每项单独捕获异常。

	Returns:
		{"closed": 整理前可见、整理后不可见的单例窗口, "visible": 整理后仍可见的（含常驻 UI）, "errors": {项: 原因}}
	"""
	import sys
	import traceback

	def visible():
		import public_ui
		import uisln
		names = set()
		handles = [ref() for ref in list(public_ui.CtrlObjsDict.values()) if ref]
		stack, seen = list(uisln.Single.__subclasses__()), set()
		while stack:
			cls = stack.pop()
			if cls in seen:
				continue
			seen.add(cls)
			stack.extend(cls.__subclasses__())
			handles.append(cls.__dict__.get("Instance"))
		for ins in handles:
			try:  # 已销毁的实例访问 ctrl 会抛 instance released
				if ins is not None and getattr(ins, "ctrl", None) is not None and not ins.ctrl.is_real_hide():
					names.add(type(ins).__module__ + "." + type(ins).__name__)
			except Exception:
				continue
		return names

	def unschedule_checkin():
		module = sys.modules.get("checkin2018_interface")
		if module is not None:  # 登录后 S_SHOW_CHECKIN4 延迟 0.2 秒才弹，不取消会在整理后再弹出
			import utils
			utils.UnSchedule(module.show_checkin_dlg)

	def new_content():
		import ww_2022checkin_msg
		ins = ww_2022checkin_msg.PalNewContent.get_ins()
		if ins and not ins.get_hide():
			ins.hide(1)

	def npc():
		import dlgnpc
		dlgnpc.hide_dlgnpc()

	out = {"closed": [], "visible": [], "errors": {}}
	try:
		before = visible()
	except Exception:
		before = None
		out["errors"]["整理前取可见窗口"] = traceback.format_exc()[-1000:]
	actions = [("取消签到延迟弹出", unschedule_checkin)]
	try:
		import ww_zlp22_chess_guide  # 游戏自带的引导清场函数，逐个调用：hide_some_base_ui 一项失败后面全不执行
		for name in ("hide_dlg_heroitem", "hide_dlg_status", "hide_dlg_dup", "hide_dlg_task", "hide_dlg_summon",
		             "hide_dlg_shop", "hide_dlg_friend", "hide_dlg_chat", "hide_dlg_factionunion", "hide_dlg_team",
		             "hide_dlg_rili", "hide_dlg_checkin", "hide_small_map", "hide_dlg_fairy", "hide_dlg_pet",
		             "hide_dlg_achieve"):
			actions.append((name, getattr(ww_zlp22_chess_guide, name)))
	except Exception:
		out["errors"]["ww_zlp22_chess_guide"] = traceback.format_exc()[-1000:]
	actions += [("PalNewContent", new_content), ("hide_dlgnpc", npc)]
	for label, action in actions:
		try:
			action()
		except Exception:
			out["errors"][label] = traceback.format_exc()[-1000:]
	try:
		after = visible()
		out["visible"] = sorted(after)
		if before is not None:
			out["closed"] = sorted(before - after)
	except Exception:
		out["errors"]["整理后取可见窗口"] = traceback.format_exc()[-1000:]
	return out


def _case_listeners():
	import traceback
	try:
		import event
		return {k: len(v.listeners) for k, v in vars(event).items() if isinstance(getattr(v, "listeners", None), list)}
	except Exception:
		return {"error": traceback.format_exc()[-2000:]}


def _case_media_start(video, frames):
	"""开始录屏（video 为 mp4 绝对路径）、开启帧采集。各项失败写进 *_error，不影响其他项。"""
	import sys
	import traceback
	out = {}
	if video:
		try:
			import C_app
			C_app.start_record_screen(video, 1, 0)  # mouse=1：录 UI 且同步绘制，0 会首帧黑屏（见 war_excellent）
			out["video"] = bool(C_app.is_record_screen())
			if not out["video"]:
				out["video_error"] = "start_record_screen 后 is_record_screen() 为假"
		except Exception:
			out["video_error"] = traceback.format_exc()[-2000:]
	if frames:
		try:
			import frame_collector
			import utils3
			if utils3.is_in_war():
				out["frames_error"] = "用例开始时已在战斗中：帧采集要在进入战斗前开启"
			else:
				sys._mhxy_case_frames_prev = id(frame_collector.get_instance()._last_battle)  # 收尾时排除开始前的上一场
				frame_collector.start_collect()
				out["frames"] = True
		except Exception:
			out["frames_error"] = traceback.format_exc()[-2000:]
	return out


def _case_media_finish(video, frames_path):
	"""停止录屏；把本场帧数据写到 frames_path 并停止采集。各项失败写进 *_error，不影响其他项。"""
	import sys
	import traceback
	out = {}
	if video:
		try:
			import C_app
			C_app.stop_record_screen()
			out["video"] = True
		except Exception:
			out["video_error"] = traceback.format_exc()[-2000:]
	if frames_path:
		try:
			import dataclasses
			import json
			import frame_collector
			c = frame_collector.get_instance()
			if c._battle:
				data = c._snapshot_battle()
			elif c._last_battle is not None and id(c._last_battle) != getattr(sys, "_mhxy_case_frames_prev", None):
				data = c._last_battle
			else:
				data = None
			if c._enabled:  # 用例结束时仍在战斗中：停止采集，避免影响之后的战斗
				frame_collector.stop_collect()
			if data is None:
				out["frames_error"] = "没有采集到本用例的战斗数据"
			else:
				with open(frames_path, "w", encoding="utf-8") as f:
					json.dump(dataclasses.asdict(data), f, ensure_ascii=False)
				out["frames"] = sum(len(t.actions) for t in data.turns)
		except Exception:
			out["frames_error"] = traceback.format_exc()[-2000:]
		finally:
			sys.__dict__.pop("_mhxy_case_frames_prev", None)
	return out
'''

# war_act／pump 用的客户端辅助函数，只在这两种步骤发送。execute_code 中顶层名字对函数不可见，所以共用的
# _case_scene 作为参数传入（见 war_act、pump 的调用行）。
# war_act 的动作分支与 ROLE_ACTS／PET_ACTS 一一对应，增删动作两处同步；先解析全部目标、道具和法宝位置，
# 再统一发包：解析失败时一个包都不发，不会只下了人物指令卡在召唤兽。
WAR_HELPERS = '''def _case_scene():
	"""确认在等待下指令阶段并给场上单位编标签。返回 (labels {wid: 标签}, pets, roster, unit 函数)；不在该阶段抛 ValueError。"""
	import utils3
	import war
	import world
	if not (utils3.is_in_war() and war.PlayerTurn >= 1 and not war.Cmds and war.ProcessFunc == war.wait_cmd):
		raise ValueError("不在等待下指令阶段，先用预设 war_idle 等待")
	units = [obj for obj in list(world.Objects.values()) if getattr(obj, "type", None) == "WARRIOR"]
	pets = list(war.summon_find_list(war.RoleID))
	labels = {war.RoleID: "self"}
	for i, wid in enumerate(pets):
		labels[wid] = "pet" if i == 0 else "pet%d" % i
	order = lambda obj: (obj.place, obj.id)
	for i, obj in enumerate(sorted([o for o in units if o.allied == 0], key=order)):
		labels[obj.id] = "e%d" % i
	for i, obj in enumerate(sorted([o for o in units if o.allied == 1 and o.id not in labels], key=order)):
		labels[obj.id] = "f%d" % i
	wids = {label: wid for wid, label in labels.items()}

	def hp(obj):
		try:
			return obj.get_member("hp_per")
		except Exception:
			return None

	roster = [{"label": labels.get(obj.id), "wid": obj.id, "name": obj.name, "allied": obj.allied, "owner": obj.owner,
		"place": obj.place, "sid": getattr(obj, "sid", None), "hp_per": hp(obj)} for obj in sorted(units, key=lambda o: o.id)]

	def unit(value, aliases=None):
		"""标签或 wid → 场上 wid；aliases 临时覆盖标签（召唤兽动作里 pet 指它自己）。"""
		names = dict(wids, **(aliases or {}))
		if isinstance(value, int):
			if value not in labels:
				raise ValueError("目标 wid %r 不在场上，可用：%s" % (value, sorted(labels)))
			return value
		if value not in names:
			raise ValueError("目标 %r 不在场上，可用：%s" % (value, sorted(names)))
		return names[value]

	return labels, pets, roster, unit


def _case_war_act(scene, role, pet):
	import traceback
	try:
		import dlgwar
		import netfabao
		import netskill
		import netwar
		import war
		labels, pets, roster, unit = scene()
		aliases = {}

		def target(spec, default):
			return unit(spec.get("target", default), aliases)

		def item_oid(value):
			import dlgitem
			item = dlgitem.item_find_by_name(value) if isinstance(value, str) else dlgitem.item_find_by_type(value)
			if not item:
				raise ValueError("背包里没有道具 %r" % (value,))
			return item.nOID

		def fabao_pos(shape):
			import dlgfabao
			for pos, value in dlgfabao.FABAO_INFO.items():
				if value == shape:
					return pos
			raise ValueError("没有装备法宝 %r" % (shape,))

		calls = []
		act = role["act"]
		if act == "attack":
			calls.append(("c_war_attack", netwar.c_war_attack, (target(role, "e0"),)))
		elif act == "magic":
			calls.append(("c_war_perform", netwar.c_war_perform, (target(role, "e0"), role["id"])))
		elif act == "sp":
			calls.append(("c_sp_perform", netskill.c_sp_perform, (target(role, "e0"), role["id"])))
		elif act == "guard":
			calls.append(("c_war_guard", netwar.c_war_guard, ()))
		elif act == "protect":
			calls.append(("c_war_protect", netwar.c_war_protect, (target(role, None),)))
		elif act == "item":
			calls.append(("c_war_item", netwar.c_war_item, (target(role, "self"), item_oid(role["item"]))))
		elif act == "fabao":
			calls.append(("C_USE_FIGHT", netfabao.C_USE_FIGHT, (target(role, "e0"), fabao_pos(role["id"]))))
		for wid in pets:
			spec = pet or {"act": "guard"}
			aliases["pet"], act = wid, spec["act"]  # 每只召唤兽的 "pet" 指它自己
			if act == "attack":
				calls.append(("c_war_summ_attack", netwar.c_war_summ_attack, (wid, target(spec, "e0"))))
			elif act == "magic":
				calls.append(("c_war_summ_perform", netwar.c_war_summ_perform, (wid, target(spec, "e0"), spec["id"])))
			elif act == "guard":
				calls.append(("c_war_summ_guard", netwar.c_war_summ_guard, (wid,)))
			elif act == "protect":
				calls.append(("c_war_summ_protect", netwar.c_war_summ_protect, (wid, target(spec, None))))
			elif act == "item":
				calls.append(("c_war_summ_item", netwar.c_war_summ_item, (wid, target(spec, "pet"), item_oid(spec["item"]))))

		turn = war.ActualTurn
		for _, func, args in calls:
			func(*args)
		war.WarriorCmdOkSet.update([war.RoleID] + pets)  # 与 PC 指令面板一致：本回合已下指令
		dlgwar.wait()
		return {"turn": turn, "sent": ["%s%r" % (name, args) for name, _, args in calls], "roster": roster,
			"pending": dlgwar.SelfID is not None}  # wait() 因身外化身、奇袭召唤兽等还要下指令而提前返回
	except Exception:
		return {"error": traceback.format_exc()[-2000:]}


def _case_pump(scene, events, token):
	"""在等待下指令阶段把事件构造成战斗命令入队，末尾加完成哨兵，再 manage_cmd 挂父子关系。

	war.Turn 在下指令阶段为 0，而 war.perform 等在 Turn == 0 时一直等待，所以入队时加 1、哨兵执行时减 1
	（增减而非赋值：期间收到服务端回合包会正常累加）。构造失败时删除本次入队的命令并减回。
	哨兵执行时把 sys._mhxy_case_pump 设为 token，本机据此判断播完。
	"""
	import sys
	import traceback
	try:
		import netwar
		import war
		import war2021_net
		labels, pets, roster, unit = scene()
		sys.__dict__.pop("_mhxy_case_pump", None)
		start = len(war.Cmds)
		war.Turn += 1
		try:
			for item in events:
				op, data = item["op"], dict(item.get("data", {}))
				for key in ("attacker_id", "victim_id", "wid"):
					if key in data:
						data[key] = unit(data[key])
				if isinstance(data.get("aid"), str):
					data["aid"] = unit(data["aid"])
				if "victims" in data:
					data["victims"] = [unit(value) for value in data["victims"]]
				if op == "perform":
					netwar.DO_S_WAR_PERFORM(data["attacker_id"], data["victims"], data["magic_id"],
						data.get("magic_desc", 0), data.get("name", ""), data.get("info", ""))
				elif op == "attack":
					war2021_net.AttackCmd(data["attacker_id"], data["victim_id"], data.get("series_attack", False))
				elif op == "wstate":
					war2021_net.WstateCmd(data["victim_id"], data.get("hurt", 0), data.get("life", 0), data.get("ward", 1),
						data.get("hp_chg", 100), data.get("hp_ext", 0), data.get("magic_id", 0))
				elif op == "wstate_split":
					war2021_net.WstateSplitCmd(data["victim_id"], data.get("split_type", 1))
				elif op == "status":
					war2021_net.StatusCmd(data["victim_id"], data["status"], data.get("eff_status", data["status"]))
				elif op == "addon":
					war2021_net.AddonCmd(data["wid"], data["pid"], data.get("turn", 2), data.get("level", 0),
						data.get("aid", 0), data.get("args", 0))
				elif op == "action_end":
					cmd = war.CCmd()
					cmd.Func = war.action_end

			def done():
				# 与 war.push_war_cmd 的包装相同；不直接用它：它在 war.WarFlag 为假时静默不入队，哨兵就永远不会执行
				war.Cmds[0].state = 1
				war.Turn -= 1
				sys._mhxy_case_pump = token
				war.next_cmd()

			sentinel = war.CCmd()
			sentinel.Func = done
			queued = [type(cmd).__name__ for cmd in war.Cmds[start:]]
			war2021_net.LastCmd = None  # 从本次第一条命令开始挂父子关系
			war2021_net.manage_cmd(war.AccTurn)
		except Exception:
			del war.Cmds[start:]
			war.Turn -= 1
			raise
		return {"queued": queued, "roster": roster}
	except Exception:
		return {"error": traceback.format_exc()[-2000:]}
'''


class CaseError(Exception):
    """用例文件或参数不合法（运行前发现，不连接客户端）。"""


# ---------- 用例文件 ----------

def load_cases(path):
    """读取用例：.json 为一个用例或用例列表；.md 取「测试用例」一节下的 json 代码块。

    Returns:
        [(来源说明, 用例 dict)]
    Raises:
        CaseError: 文件读不了、JSON 无效或找不到用例。
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise CaseError(f"读不了 {path}：{error}") from None
    blocks = spec_blocks(text) if path.suffix.lower() == ".md" else [text]
    cases = []
    for number, block in enumerate(blocks, 1):
        try:
            value = json.loads(block)
        except ValueError as error:
            raise CaseError(f"{path} 第 {number} 个用例块不是有效 JSON：{error}") from None
        for item in value if isinstance(value, list) else [value]:
            cases.append((f"{path.name}#{len(cases) + 1}", item))
    if not cases:
        raise CaseError(f"{path} 中没有用例" + ("（「测试用例」一节下没有 json 代码块）" if blocks == [] else ""))
    return cases


def spec_blocks(text):
    """取 markdown 中「测试用例」标题下（到同级或更高级标题为止）的 ```json 代码块正文。"""
    blocks, level, current = [], None, None
    for line in text.splitlines():
        heading = re.match(r"^(#+)\s", line)
        if current is None and heading and level is not None and len(heading.group(1)) <= level:
            level = None
        if level is None:
            match = SPEC_HEADING.match(line)
            if match:
                level = len(match.group(1))
            continue
        if current is None and line.strip().lower() == "```json":
            current = []
        elif current is not None and line.strip() == "```":
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def validate(case):
    """检查用例结构，返回问题列表（空表示合法）。不检查客户端代码本身。"""
    if not isinstance(case, dict):
        return ["用例必须是对象"]
    problems = []
    unknown = set(case) - CASE_FIELDS
    if unknown:
        problems.append(f"未知字段：{sorted(unknown)}")
    if not isinstance(case.get("name"), str) or not case["name"].strip():
        problems.append("缺少 name")
    names = set()
    mocks = case.get("mocks", [])
    if not isinstance(mocks, list):
        problems.append("mocks 必须是列表")
        mocks = []
    for index, mock in enumerate(mocks, 1):
        where = f"mocks[{index}]"
        if not isinstance(mock, dict) or not text_ok(mock.get("name")):
            problems.append(f"{where}：需要对象和 name")
            continue
        if mock["name"] in names:
            problems.append(f"{where}：name 重复")
        names.add(mock["name"])
        if set(mock) == {"name", "patch", "value"}:
            if not text_ok(mock["patch"]) or mock["patch"].count(".") < 1:
                problems.append(f"{where}：patch 写成 模块.属性")
            if not text_ok(mock["value"]):
                problems.append(f"{where}：value 必须是非空字符串（客户端表达式）")
        elif set(mock) == {"name", "install", "restore"}:
            if not (text_ok(mock["install"]) and text_ok(mock["restore"])):
                problems.append(f"{where}：install、restore 必须是非空字符串（客户端代码）")
        else:
            problems.append(f"{where}：只能是 name+patch+value 或 name+install+restore")
    steps = case.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps 必须是非空列表")
        steps = []
    final = case.get("finally", [])
    if not isinstance(final, list):
        problems.append("finally 必须是步骤列表")
        final = []
    for field, items in (("steps", steps), ("finally", final)):
        for index, step in enumerate(items, 1):
            problems += [f"{field}[{index}]：{problem}" for problem in validate_step(step)]
            wait = step.get("wait_for") if isinstance(step, dict) else None
            preset = wait.get("preset") if isinstance(wait, dict) else None
            if isinstance(preset, str) and preset in FRAME_PRESETS and case.get("frames") is not True:
                problems.append(f"{field}[{index}]：预设 {preset} 依赖帧采集，用例要写 frames: true")
    for flag in ("record", "frames", "clean_ui"):
        if flag in case and not isinstance(case[flag], bool):
            problems.append(f"{flag} 必须是 true 或 false")
    if "setup" in case:
        problems += [f"setup：{problem}" for problem in validate_setup(case["setup"])]
    if "settle" in case and not number_ok(case["settle"]):
        problems.append("settle 必须是秒数")
    ignores = case.get("ignore_errors", [])
    if not isinstance(ignores, list) or not all(text_ok(item) for item in ignores):
        problems.append("ignore_errors 必须是正则表达式字符串列表")
    else:
        for pattern in ignores:
            try:
                re.compile(pattern)
            except re.error as error:
                problems.append(f"ignore_errors 的正则 {pattern!r} 无效：{error}")
    return problems


def text_ok(value):
    return isinstance(value, str) and bool(value.strip())


def number_ok(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def validate_step(step):
    if not isinstance(step, dict):
        return ["步骤必须是对象"]
    kinds = [key for key in step if key in STEP_TYPES]
    if len(kinds) != 1:
        return [f"必须恰好有一个步骤类型（{'/'.join(STEP_TYPES)}），实际：{kinds or list(step)}"]
    kind = kinds[0]
    value, problems = step[kind], []
    extra = set(step) - {kind} - STEP_OPTIONS[kind]
    if extra:
        problems.append(f"{kind} 不支持选项 {sorted(extra)}")
    if kind in ("exec", "gm", "mcp", "assert", "screenshot") and not text_ok(value):
        problems.append(f"{kind} 的值必须是非空字符串")
    for option in ("save_as", "message"):
        if option in step and not text_ok(step[option]):
            problems.append(f"{option} 必须是非空字符串")
    if kind == "mcp" and not isinstance(step.get("args", {}), dict):
        problems.append("mcp 的 args 必须是对象")
    if kind == "wait_for":
        problems += validate_wait(value)
    if kind == "war_act":
        problems += validate_war_act(value)
    if kind == "pump":
        problems += validate_pump(value)
    if kind == "exec_check":
        if not isinstance(value, dict) or not text_ok(value.get("cases")) or set(value) - {"cases", "files"}:
            problems.append("exec_check 只能有 cases（定义 CASES 的客户端代码）和可选的 files")
        elif not (isinstance(value.get("files", []), list) and all(text_ok(item) for item in value.get("files", []))):
            problems.append("exec_check 的 files 必须是相对路径字符串列表")
    return problems


def validate_wait(value):
    """wait_for 的字段、类型，以及预设表达式用到的 {args.*} 是否都已提供。"""
    fields = {"expr", "preset", "args", "timeout", "interval"}
    if not isinstance(value, dict) or ("expr" in value) == ("preset" in value):
        return ["wait_for 需要 expr 或 preset 二选一"]
    problems = []
    if set(value) - fields:
        problems.append(f"wait_for 未知字段 {sorted(set(value) - fields)}")
    if "expr" in value and not text_ok(value["expr"]):
        problems.append("wait_for 的 expr 必须是非空字符串")
    args = value.get("args", {})
    if not isinstance(args, dict):
        problems.append("wait_for 的 args 必须是对象")
        args = {}
    if "preset" in value:
        if not isinstance(value["preset"], str) or value["preset"] not in PRESET_INDEX:
            problems.append(f"未知预设 {value['preset']!r}，可用：{sorted(PRESET_INDEX)}")
        else:
            needed = {key[5:] for key in PLACEHOLDER.findall(PRESET_INDEX[value["preset"]]) if key.startswith("args.")}
            if needed - set(args):
                problems.append(f"预设 {value['preset']} 缺少参数 {sorted(needed - set(args))}")
    for option in ("timeout", "interval"):
        if option in value and not number_ok(value[option]):
            problems.append(f"wait_for 的 {option} 必须是非负秒数")
    return problems


def validate_war_act(value):
    """war_act：role 必填、pet 可选，动作和必填字段见 ROLE_ACTS／PET_ACTS；wait 布尔，timeout 秒数。"""
    if not isinstance(value, dict) or "role" not in value:
        return ["war_act 需要对象，且必须有 role"]
    problems = []
    if set(value) - {"role", "pet", "wait", "timeout"}:
        problems.append(f"war_act 未知字段 {sorted(set(value) - {'role', 'pet', 'wait', 'timeout'})}")
    for who, acts in (("role", ROLE_ACTS), ("pet", PET_ACTS)):
        if who not in value:
            continue
        spec = value[who]
        if not isinstance(spec, dict) or spec.get("act") not in acts:
            problems.append(f"war_act.{who}.act 只能是 {sorted(acts)}")
            continue
        if set(spec) - {"act", "id", "target", "item"}:
            problems.append(f"war_act.{who} 未知字段 {sorted(set(spec) - {'act', 'id', 'target', 'item'})}")
        required, default = acts[spec["act"]]
        for field in required:
            if field not in spec:
                problems.append(f"war_act.{who}：{spec['act']} 需要 {field}")
        if "id" in spec and not (isinstance(spec["id"], int) and not isinstance(spec["id"], bool)):
            problems.append(f"war_act.{who}.id 必须是整数编号")
        if "item" in spec and not (text_ok(spec["item"]) or (isinstance(spec["item"], int) and not isinstance(spec["item"], bool))):
            problems.append(f"war_act.{who}.item 写道具名或造型编号")
        if "target" in spec:
            target = spec["target"]
            if not unit_ok(target):
                problems.append(f"war_act.{who}.target 写 e0/f0/self/pet 或 wid，实际 {target!r}")
        elif default is None:
            problems.append(f"war_act.{who}：{spec['act']} 必须写 target")
    if "wait" in value and not isinstance(value["wait"], bool):
        problems.append("war_act.wait 必须是 true 或 false")
    if "timeout" in value and not number_ok(value["timeout"]):
        problems.append("war_act.timeout 必须是秒数")
    return problems


def int_ok(value):
    return isinstance(value, int) and not isinstance(value, bool)


# 与 WAR_HELPERS 中 _case_scene 生成的标签一致：self、pet、pet1…、e0…、f0…（无前导零）
UNIT_LABEL = re.compile(r"self|pet(?:[1-9]\d*)?|[ef](?:0|[1-9]\d*)")


def unit_ok(value):
    """单位写法：_case_scene 生成的标签或非负整数 wid。war_act 与 pump 共用。"""
    return (int_ok(value) and value >= 0) or (isinstance(value, str) and UNIT_LABEL.fullmatch(value) is not None)


# pump 各字段的类型检查：字段名 → (检查函数, 说明)。简写和原始事件共用
PUMP_FIELD_TYPES = {
    "attacker": (unit_ok, "单位"), "attacker_id": (unit_ok, "单位"), "victim_id": (unit_ok, "单位"),
    "wid": (unit_ok, "单位"), "aid": (unit_ok, "单位"), "target": (unit_ok, "单位"),
    "victims": (lambda v: isinstance(v, list) and all(unit_ok(x) for x in v), "单位列表"),
    "magic_id": (int_ok, "整数"), "pid": (int_ok, "整数"), "hp_chg": (int_ok, "整数"), "hp_ext": (int_ok, "整数"),
    "life": (int_ok, "整数"), "ward": (int_ok, "整数"), "hurt": (int_ok, "整数"), "turn": (int_ok, "整数"),
    "level": (int_ok, "整数"), "args": (lambda v: int_ok(v) or isinstance(v, str), "整数或字符串"),
    "magic_desc": (int_ok, "整数"),
    "split_type": (int_ok, "整数"), "series_attack": (lambda v: isinstance(v, bool), "true 或 false"),
    "hits": (lambda v: int_ok(v) and v >= 1, "≥1 的整数"),
    "status": (lambda v: int_ok(v) and 0 <= v <= 100, "0～100 的整数"),
    "eff_status": (lambda v: int_ok(v) and 0 <= v <= 100, "0～100 的整数"),
    "name": (lambda v: isinstance(v, str), "字符串"), "info": (lambda v: isinstance(v, str), "字符串"),
}


def field_problems(where, data):
    """按 PUMP_FIELD_TYPES 检查 data 中已写的字段（不在表里的字段由调用方报未知字段）。"""
    problems = []
    for key, value in data.items():
        check, text = PUMP_FIELD_TYPES.get(key, (None, None))
        if check and not check(value):
            problems.append(f"{where}.{key} 必须是{text}，实际 {value!r}")
    return problems


def validate_pump(value):
    """pump：perform 简写和 events 原始事件二选一，字段见 PUMP_SHORTHAND／PUMP_OPS／PUMP_FIELD_TYPES；timeout 秒数。

    任何写法都只返回问题列表、不抛异常，保证用例不合法时整次运行 blocked 而不是崩溃。
    """
    if not isinstance(value, dict) or ("perform" in value) == ("events" in value):
        return ["pump 需要对象，perform 和 events 二选一"]
    problems = []
    if set(value) - {"perform", "events", "timeout"}:
        problems.append(f"pump 未知字段 {sorted(set(value) - {'perform', 'events', 'timeout'})}")
    if "timeout" in value and not number_ok(value["timeout"]):
        problems.append("pump.timeout 必须是秒数")
    if "perform" in value:
        spec = value["perform"]
        if not isinstance(spec, dict) or "magic_id" not in spec:
            return problems + ["pump.perform 必须是对象，且有 magic_id"]
        if set(spec) - PUMP_SHORTHAND:
            problems.append(f"pump.perform 未知字段 {sorted(set(spec) - PUMP_SHORTHAND)}")
        problems += field_problems("pump.perform", {k: v for k, v in spec.items() if k != "addons"})
        if spec.get("victims") == []:
            problems.append("pump.perform.victims 不能为空（无目标技能用 events 写）")
        addons = spec.get("addons", [])
        if not isinstance(addons, list):
            return problems + ["pump.perform.addons 必须是列表"]
        for index, addon in enumerate(addons, 1):
            where = f"pump.perform.addons[{index}]"
            if not isinstance(addon, dict) or "pid" not in addon or set(addon) - {"target", "pid", "turn", "level"}:
                problems.append(f"{where} 写成 {{target, pid, turn, level}}，pid 必填")
            else:
                problems += field_problems(where, addon)
        return problems
    events = value["events"]
    if not isinstance(events, list) or not events:
        return problems + ["pump.events 必须是非空列表"]
    for index, item in enumerate(events, 1):
        where = f"pump.events[{index}]"
        op = item.get("op") if isinstance(item, dict) else None
        if not isinstance(op, str) or op not in PUMP_OPS:
            problems.append(f"{where}.op 只能是 {sorted(PUMP_OPS)}")
            continue
        data = item.get("data", {})
        if not isinstance(data, dict) or set(item) - {"op", "data"}:
            problems.append(f"{where} 只能有 op 和 data（对象）")
            continue
        required, optional = PUMP_OPS[op]
        if set(required) - set(data):
            problems.append(f"{where}：{op} 缺少 {sorted(set(required) - set(data))}")
        if set(data) - set(required) - set(optional):
            problems.append(f"{where}：{op} 未知字段 {sorted(set(data) - set(required) - set(optional))}")
        problems += field_problems(f"{where}.data", data)
    return problems


def expand_pump(spec):
    """perform 简写 → 原始事件：出手 → 每个目标 hits 段受击（第 2 段起前置分段）→ 血条 → Buff → 行动结束。"""
    if "events" in spec:
        return spec["events"]
    perform = spec["perform"]
    victims = perform.get("victims", ["e0"])
    events = [{"op": "perform", "data": {"attacker_id": perform.get("attacker", "self"), "victims": victims,
                                         "magic_id": perform["magic_id"]}}]
    for victim in victims:
        for hit in range(perform.get("hits", 1)):
            if hit:
                events.append({"op": "wstate_split", "data": {"victim_id": victim}})
            events.append({"op": "wstate", "data": {"victim_id": victim, "life": perform.get("life", 0),
                                                    "hp_chg": perform.get("hp_chg", 100), "magic_id": perform["magic_id"]}})
    if "status" in perform:
        events += [{"op": "status", "data": {"victim_id": victim, "status": perform["status"]}} for victim in victims]
    for addon in perform.get("addons", []):
        events.append({"op": "addon", "data": {"wid": addon.get("target", "e0"), "pid": addon["pid"],
                                               "turn": addon.get("turn", 2), "level": addon.get("level", 0),
                                               "aid": perform.get("attacker", "self")}})
    return events + [{"op": "action_end"}]


def validate_setup(value):
    """setup：school [门派, 流派]、allow_destructive、teji、items、gm。"""
    fields = {"school", "allow_destructive", "teji", "items", "gm"}
    if not isinstance(value, dict) or not value:
        return ["setup 必须是非空对象"]
    problems = []
    if set(value) - fields:
        problems.append(f"未知字段 {sorted(set(value) - fields)}")
    school = value.get("school")
    if "school" in value and not (isinstance(school, list) and len(school) == 2
                                  and all(isinstance(x, int) and not isinstance(x, bool) for x in school)):
        problems.append("school 写成 [门派编号, 流派编号]")
    if "allow_destructive" in value and not isinstance(value["allow_destructive"], bool):
        problems.append("allow_destructive 必须是 true 或 false")
    if "teji" in value and not text_ok(value["teji"]):
        problems.append("teji 写特技名")
    for key in ("items", "gm"):
        if key in value and not (isinstance(value[key], list) and value[key] and all(text_ok(x) for x in value[key])):
            problems.append(f"{key} 必须是非空字符串列表")
    return problems


def render(text, context, code):
    """替换占位符：{devid}、{root} 原样代入；{vars.x}、{args.x} 在代码里代入 repr()，在其他文本里代入 str()。

    其他花括号（字典、f-string）不动。引用未定义的变量抛 KeyError。
    """
    def replace(match):
        key = match.group(1)
        if key in ("devid", "root"):
            return str(context[key])
        group, name = key.split(".", 1)
        value = context[group][name]
        return repr(value) if code else str(value)
    return PLACEHOLDER.sub(replace, text)


def render_args(value, context):
    """递归替换 mcp 参数中字符串里的占位符（按非代码文本处理）。"""
    if isinstance(value, str):
        return render(value, context, code=False)
    if isinstance(value, dict):
        return {key: render_args(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_args(item, context) for item in value]
    return value


def clip(value):
    """报告里的值：序列化后不长就原样保留，否则换成 {"clipped": 前 TEXT_LIMIT 字符, "length": 总长度}，报告仍是合法 JSON。"""
    text = json.dumps(value, ensure_ascii=False, default=repr)
    return value if len(text) <= TEXT_LIMIT else {"clipped": text[:TEXT_LIMIT], "length": len(text)}


def keep(value, context, record, field):
    """步骤记录里的值：过长时完整内容另存到媒体目录（可 json.load），报告里给出截断预览和文件路径。"""
    text = json.dumps(value, ensure_ascii=False, default=repr)
    if len(text) <= TEXT_LIMIT:
        return value
    path = media_path(context, f"_step{record['index']}_{field}.json")
    Path(path).write_text(text, encoding="utf-8")
    return {"clipped": text[:TEXT_LIMIT], "length": len(text), "file": path}


# ---------- 与客户端交互 ----------

class Client:
    """一台设备上的调用通道：握手一次，记录每个实际下发的调用（executed）。"""

    def __init__(self, devid):
        self.devid = devid
        self.executed = []
        self.ready = False

    def tool(self, name, arguments, label=None):
        """调用工具并返回载荷；先记入 executed，调用失败（含超时）时也能看到下发过什么。"""
        entry = {"tool": name, "arguments": arguments}
        if label:
            entry["label"] = label
        self.executed.append(entry)
        if not self.ready:
            mcp_http.initialize("case-runner")
            self.ready = True
        return mcp_http.call(name, arguments, handshake=False)

    def run(self, code, label=None, log_code=None):
        """execute_code，返回 {"ret", "error", "loginfo", 以及载荷附带的 ui_events／client_event}。

        log_code 用于 executed 中代替冗长的模板全文（例如“<error_watch.py 全文>”），实际仍发送 code。
        """
        arguments = {"devid": self.devid, "code": code, "need_loginfo": True}
        try:
            payload = self.tool("execute_code", arguments, label)
        finally:  # 调用失败时 executed 里也要是简写
            if log_code is not None:
                self.executed[-1]["arguments"] = dict(arguments, code=log_code)
        inner = payload.get("result", payload) if isinstance(payload, dict) and "ret" not in payload else payload
        if not isinstance(inner, dict):
            raise mcp_http.McpError(f"execute_code 结果无法识别：{str(payload)[:200]}")
        out = {"ret": inner.get("ret"), "error": inner.get("error"), "loginfo": inner.get("loginfo")}
        for key in ("ui_events", "client_event"):
            if isinstance(payload, dict) and payload.get(key):
                out[key] = payload[key]
        return out


def template(path, call):
    """模板文件全文 + 调用行，以及写进 executed 的简写。"""
    return path.read_text(encoding="utf-8") + "\n" + call, f"<{path.name} 全文>\n{call}"


# ---------- 执行 ----------

class StepFailed(Exception):
    """步骤失败：断言不成立、客户端报错、等待超时或调用失败。"""

    def __init__(self, message, record=None):
        super().__init__(message)
        self.record = record or {}


def run_case(client, root, case, settle_default, media=None):
    """执行一个用例，返回报告 dict。任何情况下都会尝试还原 Mock、停止录屏和帧采集、结束报错收集。

    Args:
        media: (目录 Path, 文件名前缀)，本用例的录像、帧数据、截图写在这里；目录按需创建。
            省略时用当前目录下的 media/case，仅供单元测试。
    """
    directory, prefix = media or (Path("media"), "case")
    context = {"devid": client.devid, "root": str(root), "vars": {}, "args": {},
               "media": (Path(directory).resolve(), prefix), "shots": 0}
    report = {"name": case["name"], "steps": [], "mocks": [], "errors": [], "unverified": []}
    start = time.time()
    failure = final_failure = None
    # 收尾要处理的内容，见 finish：video／frames 为开始阶段确实开启了的录屏路径和帧数据路径
    state = {"watching": False, "baseline": None, "patched": [], "custom": [], "video": None, "frames": None}

    def main():
        begin(client, case, context, report, state)
        if case.get("setup"):
            run_setup(client, case["setup"], report)
        for mock in case.get("mocks", []):
            if "patch" in mock:
                continue
            state["custom"].append(mock)  # 先登记：安装中途失败也要尝试还原
            result = client.run(render(mock["install"], context, code=True), f"安装 Mock {mock['name']}")
            report["mocks"].append({"name": mock["name"], "install": clip(result["ret"]), "error": result["error"]})
            if result["error"]:
                raise StepFailed(f"安装 Mock {mock['name']} 失败：{result['error']}")
        run_steps(client, root, case["steps"], context, report["steps"], "")

    try:
        failure = attempt(main)
        if case.get("finally"):  # 无论 steps 成败都执行，在还原 Mock、结束报错收集之前
            report["finally"] = []
            final_failure = attempt(lambda: run_steps(client, root, case["finally"], context, report["finally"], "F"))
    finally:
        restoration = finish(client, case, context, report, state, settle_default)
    if failure:
        report["failure"] = failure
    if final_failure:
        report["finally_failure"] = final_failure
    report["restoration"] = restoration
    report["seconds"] = round(time.time() - start, 2)
    report["status"] = ("passed" if not failure and not final_failure and not report["errors"]
                        and restoration != "unknown" else "failed")
    return report


def run_steps(client, root, steps, context, records, prefix):
    """依次执行步骤，记录追加到 records；序号带前缀（finally 步骤为 F1、F2…）。失败抛 StepFailed 等异常。"""
    for index, step in enumerate(steps, 1):
        record = {"index": f"{prefix}{index}" if prefix else index}
        records.append(record)
        began = time.time()
        try:
            run_step(client, root, step, context, record)
        finally:
            record["seconds"] = round(time.time() - began, 2)


def attempt(action):
    """执行 action，返回失败原因（成功为 None）。执行器自身的意外错误也转成失败原因，保证收尾和报告照常进行。"""
    try:
        action()
    except StepFailed as error:
        return str(error)
    except (mcp_http.McpError, OSError) as error:
        return f"{type(error).__name__}: {error}"
    except Exception as error:
        return f"执行器内部错误 {type(error).__name__}: {error}"
    return None


def helpers_call(items):
    """error_watch.py、CLIENT_HELPERS 和最后一行的结果列表拼成一次 execute_code；返回 (代码, executed 中的简写)。"""
    call = "[" + ", ".join(items) + "]"
    source = ERROR_WATCH.read_text(encoding="utf-8") + "\n" + CLIENT_HELPERS + "\n" + call
    return source, f"<{ERROR_WATCH.name} 全文>\n<CLIENT_HELPERS>\n{call}"


def media_path(context, suffix):
    """本用例的媒体文件绝对路径（正斜杠，直接给客户端用），目录按需创建。"""
    directory, prefix = context["media"]
    directory.mkdir(parents=True, exist_ok=True)
    return (directory / f"{prefix}{suffix}").as_posix()


def begin(client, case, context, report, state):
    """一次调用完成：开局整理（clean_ui，默认开）→ 开始报错收集 → 记录监听基线（有 Mock 时）→ 安装全部 patch Mock
    → 开始录屏、帧采集。

    失败抛 StepFailed。调用一发出就视为收集器和 patch Mock 都可能已生效，收尾一律尝试结束和还原；
    录屏只要请求过就在收尾停止，帧采集只有客户端确认开启了才在收尾导出。frames 时内部加装 FRAMES_NOTIFY，挡住战斗结束时的导出弹窗。
    """
    patches = [mock for mock in case.get("mocks", []) if "patch" in mock]
    if case.get("frames"):
        patches.append(FRAMES_NOTIFY)
    installs = [f"_case_install({mock['name']!r}, {mock['patch']!r}, {render(mock['value'], context, code=True)!r})"
                for mock in patches]
    video = media_path(context, ".mp4") if case.get("record") else None
    # 开局整理在开始报错收集之前：关窗口时的报错不算被测内容的
    code, log = helpers_call(["_case_clean_ui()" if case.get("clean_ui", True) else "None",
                              "error_watch_start()", "_case_listeners()" if patches or case.get("mocks") else "None",
                              "[" + ", ".join(installs) + "]",
                              f"_case_media_start({video!r}, {bool(case.get('frames'))!r})"])
    # 调用一发出就可能已生效：录屏、帧采集先登记，确认帧采集没开启时再撤销（见下方 media）
    state.update({"watching": True, "patched": patches, "video": video,
                  "frames": media_path(context, "_frames.json") if case.get("frames") else None})
    result = client.run(code, "开始：开局整理、报错收集、监听基线、patch Mock、录屏、帧采集", log)
    if result["error"] or not isinstance(result["ret"], list):
        raise StepFailed(f"用例开始阶段失败：{result['error'] or clip(result['ret'])}")
    cleaned, started, baseline, installed, media = result["ret"]
    if isinstance(cleaned, dict):
        report["clean_ui"] = cleaned
        if cleaned.get("errors"):
            report["unverified"].append(f"开局整理有 {len(cleaned['errors'])} 项失败（不影响判定），见 clean_ui.errors："
                                        f"{sorted(cleaned['errors'])}")
    if (started or {}).get("stale"):
        report["unverified"].append(f"上次未结束的报错收集残留（不属于本次）：{clip(started['stale'])}")
    if patches or case.get("mocks"):
        if isinstance(baseline, dict) and "error" not in baseline:
            state["baseline"] = baseline
        else:
            report["unverified"].append(f"读不到事件监听基线，无法核对监听残留：{clip(baseline)}")
    failed = []
    for mock, ret in zip(patches, installed):
        report["mocks"].append({"name": mock["name"], "install": clip(ret), "error": (ret or {}).get("error")})
        if (ret or {}).get("error"):
            failed.append(mock["name"])
    media = media if isinstance(media, dict) else {}
    if not media.get("frames"):
        state["frames"] = None  # 客户端确认没开启（如用例开始时已在战斗中），收尾不导出
    problems = [f"{key}：{clip(media[key])}" for key in ("video_error", "frames_error") if key in media]
    if failed:
        raise StepFailed(f"安装 Mock 失败：{failed}")
    if problems:
        raise StepFailed(f"开启录屏或帧采集失败：{problems}")


def run_setup(client, setup, report):
    """造局：先一次调用读现状，已满足的跳过，其余下发 GM 指令；结果写进 report["setup"]。失败抛 StepFailed。

    转门派（$at cs）会清空经脉，只有 allow_destructive 为真才执行。指令是否生效不在这里核对，由用例断言。
    """
    items = setup.get("items", [])
    probe = ("(lambda p: {'school': [p.get('nSchool'), p.get('nSect')], 'missing': [n for n in "
             f"{items!r} if not __import__('dlgitem').item_find_by_name(n)]}})(__import__('sdata').hero.Prop)")
    result = client.run(probe, "造局：读取门派和背包")
    record = {"state": clip(result["ret"]), "commands": []}
    report["setup"] = record
    if result["error"] or not isinstance(result["ret"], dict):
        record["error"] = clip(result["error"])
        raise StepFailed("造局：读取现状失败")
    commands = []
    if "school" in setup and result["ret"]["school"] != setup["school"]:
        if not setup.get("allow_destructive"):
            raise StepFailed(f"造局：当前门派流派 {result['ret']['school']}，切到 {setup['school']} 会清空经脉，"
                             "用例需写 allow_destructive: true")
        commands.append("$at cs {} {}".format(*setup["school"]))
    if "teji" in setup:
        commands.append(f"$at teji 1 {setup['teji']}")
    commands += [f"$at cloneobj {name}" for name in result["ret"]["missing"]]
    commands += setup.get("gm", [])
    for command in commands:
        ret = client.tool("execute_command", {"devid": client.devid, "command": command}, "造局")
        record["commands"].append({"command": command, "ret": clip(ret)})


def run_step(client, root, step, context, record):
    """执行一步并把结果写进 record；失败抛 StepFailed。"""
    kind = next(key for key in step if key in STEP_TYPES)
    record["type"] = kind
    if kind == "exec":
        result = client.run(render(step["exec"], context, code=True), f"步骤 {record['index']}")
        record.update(result_fields(result, context, record))
        if result["error"]:
            raise StepFailed(f"步骤 {record['index']} 客户端报错")
        if "save_as" in step:
            context["vars"][step["save_as"]] = result["ret"]
    elif kind == "assert":
        result = client.run(render(step["assert"], context, code=True), f"断言 {record['index']}")
        record.update(result_fields(result, context, record))
        if result["error"] or not result["ret"]:
            record["message"] = step.get("message", step["assert"])
            raise StepFailed(f"断言失败：{record['message']}")
    elif kind == "gm":
        command = render(step["gm"], context, code=False)
        record["command"] = command
        ret = client.tool("execute_command", {"devid": client.devid, "command": command})
        record["ret"] = keep(ret, context, record, "ret")
    elif kind == "mcp":
        payload = client.tool(step["mcp"], render_args(step.get("args", {}), context))
        record["ret"] = keep(payload, context, record, "ret")
        if "save_as" in step:
            context["vars"][step["save_as"]] = payload
    elif kind == "wait_for":
        wait_for(client, step["wait_for"], context, record)
    elif kind == "exec_check":
        exec_check(client, root, step["exec_check"], context, record)
    elif kind == "war_act":
        war_act(client, step["war_act"], context, record)
    elif kind == "screenshot":
        screenshot(client, step["screenshot"], context, record)
    elif kind == "pump":
        pump(client, step["pump"], context, record)


def pump(client, spec, context, record):
    """注入技能表现（设计见 spec「pump」）：一次调用入队，本机轮询哨兵标记、队列清空、回到 wait_cmd。

    超时判失败并记录当时的队列（类名、处理函数名），不自动清理：残留命令会继续播放，用例应随后 $at kill。
    """
    events = expand_pump(spec)
    token = f"pump-{time.time_ns()}"
    call = f"_case_pump(_case_scene, {events!r}, {token!r})"
    result = client.run(WAR_HELPERS + "\n" + call, f"注入 {record['index']}", f"<WAR_HELPERS>\n{call}")
    ret = result["ret"] if isinstance(result["ret"], dict) else {}
    record.update(result_fields(result, context, record))
    record["events"] = events
    if "roster" in ret:
        record.update({"roster": ret["roster"], "queued": ret.get("queued")})
    if result["error"] or "error" in ret or "queued" not in ret:
        raise StepFailed(f"注入失败：{result['error'] or ret.get('error') or clip(result['ret'])}")
    # 播完时顺手删掉标记，不留在客户端
    done = (f"(lambda s, w: s.__dict__.pop('_mhxy_case_pump', None) == {token!r} if getattr(s, '_mhxy_case_pump', None)"
            f" == {token!r} and not w.Cmds and w.ProcessFunc == w.wait_cmd else False)(__import__('sys'), __import__('war'))")
    timeout = spec.get("timeout", 15)
    try:
        wait_for(client, {"expr": done, "timeout": timeout}, context, record)
    except StepFailed as error:
        if not str(error).startswith("等待超时"):
            raise  # 等待表达式本身报错：保留原错误，不误报为超时
        # 后续步骤（含用例里的 $at kill）不会再执行，要手动结束战斗。哨兵是否执行看标记：没执行时 war.Turn 仍多 1
        probe = ("(lambda w, s: {'turn': w.Turn, 'process': getattr(w.ProcessFunc, '__name__', repr(w.ProcessFunc)),"
                 " 'marker': getattr(s, '_mhxy_case_pump', None), 'queue': [(type(c).__name__,"
                 " getattr(getattr(c, 'Func', None), '__name__', '')) for c in w.Cmds]})"
                 "(__import__('war'), __import__('sys'))")
        state = {}
        try:
            result = client.run(probe, f"注入 {record['index']} 超时：读取状态")
            if result["error"] or not isinstance(result["ret"], dict):
                record["queue"] = f"读取失败：{clip(result['error'] or result['ret'])}"
            else:
                state = result["ret"]  # 判断用原始值；报告里只裁剪队列列表，避免整个状态被截成字符串
                record["queue"] = dict(state, queue=clip(state.get("queue")))
        except (mcp_http.McpError, OSError) as probe_error:
            record["queue"] = f"读取失败：{probe_error}"
        if not state:
            detail = "客户端状态未知"
        elif state.get("marker") == token:
            detail = "哨兵已执行（Turn 已减回），但队列未清空或未回到 wait_cmd，可能排进了服务端回合协议"
        else:
            detail = f"哨兵未执行，war.Turn 仍含注入时加的 1（当前 {state.get('turn')}）"
        raise StepFailed(f"pump 超时（{timeout} 秒）：{detail}，状态见步骤记录 queue；"
                         "后续步骤不再执行，需手动 $at kill 结束战斗") from None


def war_act(client, spec, context, record):
    """一次调用下完人物和全部在场召唤兽的指令，再按 wait 等到下一回合的等待下指令阶段或战斗结束。"""
    call = f"_case_war_act(_case_scene, {spec['role']!r}, {spec.get('pet')!r})"
    result = client.run(WAR_HELPERS + "\n" + call, f"回合指令 {record['index']}", f"<WAR_HELPERS>\n{call}")
    ret = result["ret"] if isinstance(result["ret"], dict) else {}
    record.update(result_fields(result, context, record))
    if "roster" in ret:
        # 场面映射不截断：对照帧数据和日志要用全量。ret 之后会被等待结果覆盖，所以单独保存
        record.update({"roster": ret["roster"], "sent": ret.get("sent")})
    if result["error"] or "error" in ret or "turn" not in ret:
        raise StepFailed(f"下指令失败：{result['error'] or ret.get('error') or clip(result['ret'])}")
    if ret.get("pending"):
        raise StepFailed("指令已发出，但还有单位等指令（如身外化身、奇袭召唤兽），war_act 不支持这些单位")
    if spec.get("wait", True):
        expr = f"not __import__('utils3').is_in_war() or ({WAR_WAITING} and __import__('war').ActualTurn > {ret['turn']})"
        wait_for(client, {"expr": expr, "timeout": spec.get("timeout", 90)}, context, record)


def screenshot(client, label, context, record):
    """截渲染画面（utils.screenshot，后台窗口也能截）到媒体目录，本机等文件出现。不直接调 C_app.save_screen（会崩溃）。"""
    context["shots"] += 1
    path = media_path(context, f"_shot{context['shots']}.jpg")  # 文件类型参数 2 产出 JPEG（真机核实）
    code = ("__import__('utils').screenshot(None, (0, 0, __import__('sdata').env.SCREENW, "
            f"__import__('sdata').env.SCREENH, 2, 90), {path!r})")
    result = client.run(code, f"截图 {record['index']}")
    record.update(result_fields(result, context, record))
    record.update({"label": label, "path": path})
    if result["error"]:
        raise StepFailed("截图调用报错")
    if not wait_file(Path(path), SHOT_WAIT):
        raise StepFailed(f"{SHOT_WAIT} 秒内没有生成截图文件：{path}")


def wait_file(path, timeout):
    """本机等文件出现且大小连续两次（间隔 1 秒）不变、不为 0；超时返回 False。"""
    deadline, last = time.time() + timeout, -1
    while time.time() < deadline:
        size = path.stat().st_size if path.exists() else -1
        if size > 0 and size == last:
            return True
        last = size
        time.sleep(1)
    return False


def result_fields(result, context, record):
    fields = {"ret": keep(result["ret"], context, record, "ret")}
    for key in ("error", "loginfo", "ui_events", "client_event"):
        if result.get(key):
            fields[key] = keep(result[key], context, record, key)
    return fields


def wait_for(client, spec, context, record):
    """在本机轮询客户端表达式直到为真；超时或表达式报错即失败。不在客户端主线程等待。"""
    args = spec.get("args", {})
    if "preset" in spec:
        record["preset"] = spec["preset"]
        expr = render(PRESET_INDEX[spec["preset"]], dict(context, args=args), code=True)
    else:
        expr = render(spec["expr"], context, code=True)
    timeout, interval = spec.get("timeout", 30), spec.get("interval", 0.5)
    deadline, polls = time.time() + timeout, 0
    while True:
        polls += 1
        # 只记录第一次轮询，避免 executed 被重复的轮询淹没
        result = client.run(expr, f"等待 {record['index']}") if polls == 1 else client_quiet(client, expr)
        if result["error"]:
            record.update(result_fields(result, context, record))
            raise StepFailed(f"等待条件报错（第 {polls} 次轮询）")
        if result["ret"]:
            record.update({"ret": keep(result["ret"], context, record, "ret"), "polls": polls})
            return
        if time.time() >= deadline:
            record.update({"ret": keep(result["ret"], context, record, "ret"), "polls": polls})
            raise StepFailed(f"等待超时（{timeout} 秒，{polls} 次轮询）：{expr}")
        time.sleep(interval)


def client_quiet(client, expr):
    """与 client.run 相同，但不追加 executed 记录（轮询的重复调用）。"""
    size = len(client.executed)
    try:
        return client.run(expr)
    finally:
        del client.executed[size:]


def exec_check(client, root, spec, context, record):
    """改动执行检查：目标行取自 diff_lines.collect，用 exec_trace.py 在一次调用里跑完 CASES。

    没执行到的行写进 record["missing"]，由 run_case 汇总到 unverified，不算失败；用例报错算失败。
    """
    import diff_lines  # 只有这一步需要 svn 和 3.11 的行号表，延迟导入
    try:
        rels = spec.get("files") or diff_lines.changed_py_files(root)
        collected = diff_lines.collect(root, rels)
    except diff_lines.precommit.PrecheckError as error:
        raise StepFailed(f"计算目标行失败：{error}") from None
    record["targets"] = {"total": collected["total"], "skipped": collected["skipped"]}
    record["warnings"] = collected["warnings"]  # 例如本机不是 3.11，行号可能对不上；finish 汇总进 unverified
    if collected["skipped"]:
        # exec-check.md：skipped 不为空先报告，有语法错误先修好；不能带着漏检的文件判通过
        raise StepFailed(f"有文件无法计算目标行：{collected['skipped']}")
    call = f"exec_check_start({collected['files']!r}, CASES)"
    body = render(spec["cases"], context, code=True) + "\n" + call  # 用例定义在前，调用在最后一行
    code, log = template(EXEC_TRACE, body)
    result = client.run(code, f"执行检查 {record['index']}", log)
    record.update(result_fields(result, context, record))
    ret = result["ret"] if isinstance(result["ret"], dict) else {}
    if result["error"] or "abort" in ret:
        raise StepFailed(f"执行检查没有运行：{result['error'] or ret.get('abort')}")
    record["missing"] = {path: lines for path, lines in ret.get("missing", {}).items() if lines}
    bad = {name: text for name, text in ret.get("results", {}).items() if text != "ok"}
    if bad:
        raise StepFailed(f"执行检查用例报错：{sorted(bad)}")


def finish(client, case, context, report, state, settle_default):
    """收尾：等待延迟回调，逆序还原自定义 Mock，再用一次调用还原 patch Mock、核对监听、结束报错收集。

    state 由 run_case／begin 填写：watching（收集器可能已挂上）、baseline（监听基线）、patched、custom
    （可能已安装的 Mock）。每一项单独捕获失败，前一项失败不影响后一项；还原失败或无法核对的记为 unknown。

    Returns:
        restoration：restored／unknown／not_needed（没有 Mock）。
    """
    time.sleep(case.get("settle", settle_default))
    restored = []

    def entry_of(mock):
        entry = next((item for item in report["mocks"] if item["name"] == mock["name"]), None)
        if entry is None:
            entry = {"name": mock["name"]}
            report["mocks"].append(entry)
        return entry

    # 自定义 Mock 逐个逆序还原（代码任意，不能合并）
    for mock in reversed(state["custom"]):
        entry = entry_of(mock)
        try:
            result = client.run(render(mock["restore"], context, code=True), f"还原 Mock {mock['name']}")
            ok = not result["error"] and result["ret"] is True  # restore 代码最后一行要返回核对结果 True
            entry.update({"restore": clip(result["ret"]), "restore_error": result["error"], "restored": ok})
        except Exception as error:  # 含 restore 代码引用了未赋值的 {vars.*}：记为未还原，继续后面的收尾
            entry.update({"restore_error": f"{type(error).__name__}: {error}", "restored": False})
        restored.append(entry["restored"])

    # 停止录屏、导出帧数据（先于还原：帧采集停用后才还原导出弹窗的 Mock）、patch Mock 逆序还原、核对监听、
    # 结束报错收集：合并成一次调用
    patches = list(reversed(state["patched"]))
    media = state["video"] or state["frames"]
    if patches or state["baseline"] is not None or state["watching"] or media:
        items = [f"_case_media_finish({state['video']!r}, {state['frames']!r})" if media else "None",
                 "[" + ", ".join(f"_case_restore({mock['name']!r})" for mock in patches) + "]",
                 "_case_listeners()" if state["baseline"] is not None else "None",
                 "error_watch_finish()" if state["watching"] else "None"]
        code, log = helpers_call(items)
        try:
            result = client.run(code, "收尾：停止录屏和帧采集、还原 patch Mock、核对监听、结束报错收集", log)
            if result["error"] or not isinstance(result["ret"], list):
                raise mcp_http.McpError(f"收尾调用失败：{result['error'] or clip(result['ret'])}")
            finished, restores, after, collected = result["ret"]
        except (mcp_http.McpError, OSError) as error:
            finished, restores, after, collected = None, [None] * len(patches), None, None
            report["unverified"].append(f"{error}；patch Mock、录屏和帧采集状态不明，报错收集器可能仍挂在客户端上")
        if media:
            collect_media(state, finished if isinstance(finished, dict) else {}, report)
        for mock, ret in zip(patches, restores):
            entry = entry_of(mock)
            ret = ret if isinstance(ret, dict) else {}
            # 安装在登记之前就失败（模块找不到、value 报错）时客户端没有任何改动，不需要还原
            never = bool(entry.get("error")) and ret.get("reason") == "没有安装记录"
            entry.update({"restore": clip(ret), "restored": bool(ret.get("restored") or never)})
            restored.append(entry["restored"])
        if state["baseline"] is not None and isinstance(after, dict):
            if "error" in after:
                report["unverified"].append(f"核对事件监听失败：{clip(after['error'])}")
            else:
                grown = {name: [state["baseline"].get(name, 0), count] for name, count in after.items()
                         if count > state["baseline"].get(name, 0)}
                if grown:
                    report["unverified"].append(f"事件监听比基线多（前后数量，可能是被测代码正常注册，也可能是 Mock 残留）：{grown}")
        if isinstance(collected, dict):
            texts = [item.get("text", str(item)) for item in collected.get("errors", [])]
            # 用例声明的已知无关报错（如客户端既有的资源告警）：仍写进报告备查，但不计入 errors、不判失败
            ignores = [re.compile(pattern) for pattern in case.get("ignore_errors", [])]
            report["ignored_errors"] = [text for text in texts if any(p.search(text) for p in ignores)]
            report["errors"] = [text for text in texts if text not in report["ignored_errors"]]
            if report["ignored_errors"]:
                report["unverified"].append(f"按 ignore_errors 忽略了 {len(report['ignored_errors'])} 条报错，原文见 ignored_errors")
            if collected.get("dropped"):
                report["unverified"].append(f"报错过多，另有 {collected['dropped']} 条被丢弃")

    for step in report["steps"] + report.get("finally", []):
        if step.get("type") == "screenshot" and step.get("path") and Path(step["path"]).exists():
            report.setdefault("media", {}).setdefault("screenshots", []).append(
                {"label": step["label"], "path": step["path"]})
        for path, lines in step.get("missing", {}).items():
            report["unverified"].append(f"步骤 {step['index']} 执行检查未执行到：{path} {lines}")
        for text in step.get("warnings", []):
            report["unverified"].append(f"步骤 {step['index']} 目标行计算警告：{text}")
    if not restored:
        return "not_needed"
    return "restored" if all(restored) else "unknown"


def collect_media(state, finished, report):
    """核对收尾调用里录屏和帧数据的结果，本机等 mp4 写完；文件路径写进 report["media"]，问题记入 unverified。

    录像和帧数据是证据而不是判定条件，拿不到只记 unverified，不判用例失败。
    """
    files = report.setdefault("media", {})
    for key in ("video_error", "frames_error"):
        if key in finished:
            report["unverified"].append(f"{key}：{clip(finished[key])}")
    if state["video"]:
        if wait_file(Path(state["video"]), VIDEO_WAIT):
            files["video"] = state["video"]
        else:
            report["unverified"].append(f"停止录屏后 {VIDEO_WAIT} 秒内没有得到完整的 mp4：{state['video']}")
    if state["frames"] and "frames" in finished:
        files.update({"frames": state["frames"], "frame_actions": finished["frames"]})


def summarize(reports, blocked=None):
    """汇总为 test 结果字段（status／cases／errors／unverified／restoration）加明细。"""
    if blocked:
        return {"status": "blocked", "cases": [], "errors": [blocked], "unverified": [],
                "restoration": "not_needed", "results": [], "executed": []}
    restorations = {item["restoration"] for item in reports}
    restoration = ("unknown" if "unknown" in restorations else
                   "restored" if "restored" in restorations else "not_needed")
    return {
        "status": "passed" if all(item["status"] == "passed" for item in reports) else "failed",
        "cases": [f"{item['name']}：{item['status']}（{item['seconds']} 秒）"
                  + (f"，{item['failure']}" if item.get("failure") else "")
                  + (f"，finally 失败：{item['finally_failure']}" if item.get("finally_failure") else "")
                  for item in reports],
        "errors": [f"{item['name']}：{text}" for item in reports for text in item["errors"]],
        "unverified": [f"{item['name']}：{text}" for item in reports for text in item["unverified"]],
        "restoration": restoration,
        "results": reports,
    }


def run(root, devid, sources, settle=2.0, init=True, run_id=None):
    """校验全部用例后依次执行，返回汇总报告。用例文件有问题时不连接客户端，直接 blocked。

    Args:
        run_id: 运行编号，决定媒体目录 reports/<run_id>/ 和报告文件名；省略时取当前时间。
    """
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    cases = []
    try:
        for source in sources:
            cases += load_cases(source)
    except CaseError as error:
        return summarize([], str(error))
    problems = [f"{where}：{problem}" for where, case in cases for problem in validate(case)]
    if problems:
        return summarize([], "用例文件不合法：" + "；".join(problems))
    client = Client(devid)
    if init:
        try:
            client.tool("init_client", {"devid": devid})
        except (mcp_http.McpError, OSError) as error:
            report = summarize([], f"init_client 失败：{error}")
            report["executed"] = client.executed
            return report
    media_dir = Path(root) / REPORT_DIR / run_id
    reports = [run_case(client, root, case, settle, (media_dir, f"case{number}"))
               for number, (_, case) in enumerate(cases, 1)]
    report = summarize(reports)
    report["executed"] = client.executed
    return report


# ---------- 用例模板与检索 ----------

# 技能导表的条目行：`编号 : ( "名字", 基础编号, ...` 和 `编号:( "名字", ...`
PERFORM_LINE = re.compile(r'^\s*(\d+)\s*:\s*\(\s*"([^"]*)"\s*,\s*(\d+)', re.M)
SP_LINE = re.compile(r'^\s*(\d+)\s*:\s*\(\s*"([^"]*)"', re.M)


def load_templates():
    """读取 assets/cases 下全部模板：[{path, description, keywords, case}]。模板写错直接抛异常（单测保证不会）。"""
    templates = []
    for path in sorted(TEMPLATE_DIR.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        templates.append({"path": str(path), "description": data["description"],
                          "keywords": data["keywords"], "case": data["case"]})
    return templates


def search(root, terms):
    """先找全部关键词都命中（名字、说明、关键词）的模板；没有时按技能名查导表，生成战斗用例骨架。

    Returns:
        {"templates": [...]}，或 {"templates": [], "skills": [...], "skeletons": [...], "note": 说明}。
    """
    found = []
    for item in load_templates():
        text = " ".join([item["case"]["name"], item["description"], *item["keywords"]])
        if all(term in text for term in terms):
            found.append(item)
    if found:
        return {"templates": found}
    skills = find_skills(root, terms)
    return {"templates": [], "skills": skills, "skeletons": [skeleton(skill) for skill in skills],
            "note": "骨架只保证结构合法：角色要会这个技能（不会就在 setup 里补门派、特技），断言按被测内容补；"
                    "特技在帧数据里的 magic_id 按 sp_id+3000 推算，尚未真机核实；"
                    "fightN 的敌方机器人没有武器层等装备层，测造型分层要观察主角或指定造型"}


def find_skills(root, names):
    """按技能名在 infoskillperform2021（门派法术）和 infosp（特技）里精确查编号。法术只取编号等于基础编号的条目。"""
    found = []
    perform = Path(root) / "data" / "infoskillperform2021.py"
    special = Path(root) / "data" / "infosp.py"
    perform_text, special_text = (read_source(path) for path in (perform, special))
    for name in names:
        for key, title, base in PERFORM_LINE.findall(perform_text):
            if title == name and key == base:
                found.append({"name": name, "kind": "magic", "id": int(key), "magic_id": int(key)})
        for key, title in SP_LINE.findall(special_text):
            if title == name:
                found.append({"name": name, "kind": "sp", "id": int(key), "magic_id": int(key) + 3000})
    return found


def read_source(path):
    """按 Python 源码声明的编码读取（兼容历史 GBK 导表）；文件不存在时返回空串。"""
    if not path.exists():
        return ""
    with tokenize.open(path) as file:
        return file.read()


def skeleton(skill):
    """战斗用例骨架：进战斗 → 放技能（召唤兽防御）→ 等这次出手播完；退战放在 finally。

    fightN 造出的敌方机器人没有武器层等装备层，测造型分层的用例要把主角或指定造型作为观察对象。
    """
    return {
        "name": f"{skill['name']} 出手表现",
        "frames": True,
        "steps": [
            {"assert": "not __import__('utils3').is_in_war()", "message": "开始前不在战斗中"},
            {"gm": "$at fightN 2"},
            {"wait_for": {"preset": "war_idle", "timeout": 60}},
            # wait: false：不等整回合播完，由 war_action 等这次出手播完就继续（之后的截图、断言才在出手时刻）
            {"war_act": {"role": {"act": skill["kind"], "id": skill["id"], "target": "e0"}, "wait": False}},
            {"wait_for": {"preset": "war_action", "args": {"magic_id": skill["magic_id"], "n": 1}, "timeout": 30}},
        ],
        # 失败也退战，避免下一轮第 1 步因还在战斗中而失败
        "finally": [
            {"gm": "$at kill"},
            {"wait_for": {"preset": "war_out", "timeout": 30}},
        ],
    }


def save(root, report, run_id):
    directory = Path(root) / REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (run_id + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="真机用例执行器")
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="执行用例文件（.json）或 spec 中「测试用例」一节（.md）")
    runner.add_argument("--root", required=True, help="项目根目录（mhimage）")
    runner.add_argument("--devid", required=True)
    runner.add_argument("--settle", type=float, default=2.0, help="收尾前等待延迟回调的秒数，用例可用 settle 覆盖")
    runner.add_argument("--no-init", action="store_true", help="同一任务已调用过 init_client 时跳过")
    runner.add_argument("sources", nargs="+")
    finder = sub.add_parser("search", help="按关键词找用例模板；没有模板时按技能名生成战斗用例骨架")
    finder.add_argument("--root", required=True, help="项目根目录（mhimage），用来读技能导表")
    finder.add_argument("terms", nargs="+")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "search":
        print(json.dumps(search(root, args.terms), ensure_ascii=False, indent=1))
        return 0
    run_id = time.strftime("%Y%m%d-%H%M%S")
    report = run(root, args.devid, args.sources, args.settle, not args.no_init, run_id)
    report["report_path"] = str(save(root, report, run_id))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return {"passed": 0, "failed": 1}.get(report["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
