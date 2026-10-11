# Smartisan-inspired 轻拟物设计系统

## 设计命题

PDF Studio Lite 的视觉记忆点是“精密纸张工作台”：内容层保持安静，拟物深度只出现在能点击、拖动或输入的功能层。三栏信息架构、Windows 窗口边框和键盘习惯保持不变。

## 色彩

| 角色 | 浅色 | 深色 | 用途 |
| --- | --- | --- | --- |
| Canvas | `#E9E9E6` | `#1D1E20` | 页面工作台 |
| Surface | `#F7F7F4` | `#27282A` | 面板与菜单 |
| Primary text | `#292927` | `#F2F2EF` | 正文与标题 |
| Secondary text | `#676762` | `#B4B4AE` | 辅助说明 |
| Accent | `#E66A1F` | `#F07A32` | 唯一主要动作、开关开启和选中反馈 |
| Destructive | `#B83A32` | `#D35A50` | 删除与不可逆警示 |

实测对比度：浅色主文字 13.58:1，浅色辅助文字 5.30:1，深色主文字 14.87:1，深色辅助文字 7.08:1。白色粗体位于橙色主要按钮上为 3.26:1，满足大号或粗体控制文字 3:1 的要求。

## 字体与尺寸

- 控件字体：`Segoe UI Variable`，中文按系统字形回退到 `Microsoft YaHei UI`。
- 桌面正文 13px，辅助信息不低于 11px。
- 普通控件高度 30px，自定义开关默认 58x32px，均保留清晰键盘焦点。
- 间距使用 4px 基础网格，常用 8、12、16、24px。

## 材质规则

- 输入框：内凹，上缘略暗；获得焦点时使用橙色焦点环。
- 普通按钮：轻微金属高光与底部暗边；按下时高光反转并下沉 2px。
- 主要按钮：只保留一个橙色焦点，不让多个橙色按钮争夺注意力。
- 页面缩略图：纸张为白色，选中使用克制橙色描边，不添加厚重拟物外壳。
- 阴影不用于表达纯装饰，只表达可按压、内凹或纸张悬浮关系。

## 自定义开关

`SkeuomorphicSwitch` 使用四层 QPainter 绘制：金属轮廓、内凹轨道、状态色、同心纹实体旋钮。动画为 180ms `InOutCubic` 水平移动，无弹跳；支持鼠标、Space/Enter、Hover、Pressed、Disabled 与键盘焦点。

## HIG 转译

- `accessibility.md › Vision / Mobility`：正文对比度达到 4.5:1，状态不只依赖颜色，桌面控件不低于 20x20pt。
- `layout.md › Visual hierarchy`：相关参数分组，使用留白与渐进披露，窗口缩放时不移除功能。
- `typography.md › Ensuring legibility`：使用系统字体和 Regular/Semibold 层级，避免小字号 Light。
- `color.md › Best practices`：橙色只表示主要动作和开启状态，浅色与深色使用语义化 Token。
- `buttons.md` 与 `toggles.md`：自定义外观保留标准按钮/开关行为、焦点和清晰状态。
- `windows.md`：保留 Windows 11 原生窗口框架，不仿制 macOS 窗口按钮。
