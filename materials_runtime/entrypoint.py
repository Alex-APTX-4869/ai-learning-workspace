"""以 python -I 执行；直接登记可信解析包，不读取整个项目目录。"""
from pathlib import Path
import sys
from types import ModuleType

package = ModuleType("materials_runtime")
package.__path__ = [str(Path(__file__).resolve().parent)]
sys.modules["materials_runtime"] = package
from materials_runtime.worker import main

main()
