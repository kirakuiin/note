# -*- coding: utf-8 -*-
"""
编码转换工具：将 GB18030 编码的文件转为 UTF-8

用法: python convert_encoding.py <file_path>
"""
import sys
import os


def convert_gb18030_to_utf8(file_path: str):
    """将文件从 GB18030 转换为 UTF-8 编码"""
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return False
    
    try:
        # 读取 GB18030 编码的内容
        with open(file_path, 'r', encoding='gb18030') as f:
            content = f.read()
        
        # 写入 UTF-8 编码
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"转换成功: {file_path}")
        return True
    
    except UnicodeDecodeError as e:
        print(f"编码错误，文件可能不是 GB18030 编码: {e}")
        return False
    except Exception as e:
        print(f"转换失败: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python convert_encoding.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    success = convert_gb18030_to_utf8(file_path)
    sys.exit(0 if success else 1)
