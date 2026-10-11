# SkeuomorphicSwitch

正式实现：`app/ui/components/skeuomorphic_switch.py`

参考视频验证的结构为金属外框、内凹轨道、深灰/橙色状态层和带同心圆加工纹的金属旋钮。控件在任意 DPI 下由 QPainter 重绘，不依赖位图切片。

动画时长 180ms；开启为橙色、关闭为石墨灰；按压使旋钮下沉 1px；焦点环和形状共同表达状态，避免仅靠颜色。
