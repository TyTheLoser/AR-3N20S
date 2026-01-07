# Qt Monitor (PySide6)

## Environment

Use conda to manage the env:

- `conda create -n arizon_force_sensor python=3.10`
- `conda activate arizon_force_sensor`

## Install

- `pip install -r requirements.txt`

## Run

- `python D:\APP\ARIZON_Force_sensor\qt_app.py`
- `python D:\APP\ARIZON_Force_sensor\six_axis_force_sensor.py`

## six_axis_force_sensor 用法

示例已放在 `six_axis_force_sensor.py` 的 `__main__` 中，命令行直接执行即可。

常用操作：

- `get_wrench()` / `get_forces()`：读取力（Fx/Fy/Fz）
- `bias()`：软件清零（后续读取自动减去偏置）
- `unbias()`：清除偏置
