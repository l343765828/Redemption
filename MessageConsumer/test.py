from pathlib import Path
from Model.Config import DELTA_USER


def test():
    here = Path(__file__).resolve().parent
    order_model_path = (here.parent / "Model" / "OrderPayload.py").resolve()

    print(f"打印here：", here)
    print(f"打印here：", here.parent)
    print(f"是否存在：", order_model_path.exists())


def test2():
    here = Path(__file__).resolve().parent
    project_dir = here.parent.parent

    print(f"打印：", project_dir)

def test3():
    print(f"打印：",DELTA_USER)

def test4():
    gpv=3100-1000
    virtual_width = gpv // 1000
    print(virtual_width)

if __name__ == "__main__":
    test4()
