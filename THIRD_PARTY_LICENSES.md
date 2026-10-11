# 第三方依赖与分发说明

- PySide6 / Qt for Python：LGPLv3 / GPLv3 / 商业许可。当前项目按 LGPLv3 动态链接方式分发，必须随发行包保留相应许可文本，并允许用户替换 LGPL 库。
- PyMuPDF：AGPLv3 或 Artifex 商业许可。向第三方分发闭源商业软件前必须取得合适的商业许可，或使整个应用符合 AGPLv3。
- Pillow：HPND License，可再分发并须保留许可声明。
- pikepdf：MPL-2.0；其依赖 qpdf 使用 Apache-2.0，可随应用分发并保留声明。
- PyInstaller：GPLv2 with bootloader exception，可用于打包不同许可的软件。
- pytest：MIT，仅用于开发测试。

此清单不是法律意见。正式商业发布前应由发行方复核依赖的当前许可证文本与打包内容。

