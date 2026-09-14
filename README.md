# PDF 递归批量解包工具：Windows 零基础使用教程

本教程从安装 Python 开始。使用者不需要会写代码，按顺序操作即可。

这个工具会递归扫描当前文件夹和全部子文件夹中的 PDF，并依次尝试把它们作为 ZIP、7z、RAR 解压。发现 MP4 后，MP4 会放到起始 PDF 的同一目录；中间文件和临时文件夹会自动清理。

## 第一步：安装 Python

### 1. 下载 Python

1. 打开浏览器。
2. 进入 Python 官方 Windows 下载页面：<https://www.python.org/downloads/windows/>。
3. 建议下载 Python 3.11 的 64 位安装程序，即 `Windows installer (64-bit)`。
4. 不要安装 Python 3.8 或更旧版本。本工具支持 Python 3.9 及以上版本。

### 2. 安装 Python

双击下载好的 Python 安装程序。

在安装窗口底部，务必勾选：

```text
Add python.exe to PATH
```

然后单击：

```text
Install Now
```

等待安装完成。如果最后出现 `Disable path length limit`，可以单击一次，然后关闭安装窗口。

### 3. 检查 Python 是否安装成功

1. 按键盘上的 `Win + R`。
2. 输入 `cmd`。
3. 按回车。
4. 在黑色窗口中输入：

```bat
python --version
```

如果显示类似以下内容，说明安装成功：

```text
Python 3.11.x
```

如果提示找不到 `python`，再试：

```bat
py --version
```

如果仍然找不到，请重新安装 Python，并确认安装时勾选了 `Add python.exe to PATH`。

## 第二步：安装 WinRAR（用于处理 RAR）

ZIP 和 7z 可以由 Python 直接解压。要处理 RAR，电脑还需要安装 WinRAR。

把 WinRAR 安装到默认目录即可。程序会自动寻找：

```text
C:\Program Files\WinRAR\UnRAR.exe
C:\Program Files (x86)\WinRAR\UnRAR.exe
```

如果确定文件中不会出现 RAR，可以跳过这一步；ZIP 和 7z 功能不受影响。

## 第三步：准备工具和 PDF

把下面两个文件放进需要处理的总文件夹：

```text
pdf_zip_unpacker.py
requirements.txt
```

PDF 可以放在同一个目录，也可以放在任意子文件夹中。例如：

```text
D:\待处理文件\
├─ pdf_zip_unpacker.py
├─ requirements.txt
├─ 暖父1女儿上学.pdf
├─ 暖父2映日荷花别样红.pdf
├─ 第一批\
│  ├─ 文件1.pdf
│  └─ 文件2.pdf
└─ 第二批\更多文件\
   └─ 文件3.pdf
```

双击运行时，程序会扫描 `pdf_zip_unpacker.py` 所在文件夹，以及下面所有层级的子文件夹。

## 第四步：第一次运行

直接双击：

```text
pdf_zip_unpacker.py
```

第一次运行会显示：

```text
首次运行：正在自动安装 ZIP/7z/RAR 解压依赖……
```

这是正常现象。程序正在安装：

```text
pyzipper
py7zr
```

首次安装需要连接网络。根据网络速度，可能需要几十秒或几分钟，请不要关闭窗口。

程序会根据 Python 版本自动选择兼容依赖：

- Python 3.9 使用 `py7zr 1.0.0`。
- Python 3.10 及以上使用 `py7zr 1.1.3`。
- 如果 pip 太旧，程序会尝试自动升级 pip 后再次安装。

安装成功后，程序会自动开始扫描 PDF。以后再次运行时通常不需要重复安装。

## 第五步：等待程序处理

程序会对每个起始 PDF 执行以下操作：

1. 在临时目录中创建 `.zip` 后缀入口，原 PDF 不会被改名。
2. 按 `ZIP → 7z → RAR` 顺序尝试解压。
3. 依次尝试以下密码：

```text
lovelili
lovelily
lililove
lililovesmenot
Ilovelilinomore
```

4. 解压后递归搜索所有子文件夹。
5. 如果发现 PDF、ZIP、7z 或 RAR，继续逐层解压。
6. 如果发现 MP4，停止当前文件的递归，并处理下一个起始 PDF。

处理大型文件或层数很多的文件时，需要等待一段时间。运行过程中不要关闭窗口。

## 第六步：查看结果

找到的 MP4 会直接放到起始 PDF 的同一目录。

例如原文件是：

```text
D:\待处理文件\第一批\示例.pdf
```

找到 `成片.mp4` 后，目录会变成：

```text
D:\待处理文件\第一批\示例.pdf
D:\待处理文件\第一批\成片.mp4
```

程序不会留下 `level_001`、`_unpacked_results` 等解压文件夹。

- 原始 PDF 不会被删除。
- 中间 PDF、ZIP、7z、RAR 和解压目录都会自动清理。
- 已存在同名且内容相同的 MP4 时，不会重复复制。
- 已存在同名但内容不同的 MP4 时，新文件会使用 `_2.mp4`、`_3.mp4` 等名称，避免覆盖旧文件。

全部处理结束后，窗口会显示汇总。按回车键关闭窗口。

## 如果双击 `.py` 没有反应

可能是 `.py` 没有关联到 Python。

方法一：

1. 右键单击 `pdf_zip_unpacker.py`。
2. 选择“打开方式”。
3. 选择 Python。
4. 如果列表中没有 Python，选择“在这台电脑上查找其他应用”，找到 Python 安装目录中的 `python.exe`。

方法二：在工具目录运行命令。

1. 打开存放工具的文件夹。
2. 单击文件管理器顶部地址栏。
3. 输入 `cmd` 并按回车。
4. 输入：

```bat
python pdf_zip_unpacker.py
```

如果 `python` 不可用，输入：

```bat
py pdf_zip_unpacker.py
```

## 自动安装失败时的处理方法

在工具目录打开 `cmd`，先执行：

```bat
python -m pip install --upgrade pip
```

然后执行：

```bat
python -m pip install -r requirements.txt
```

如果电脑使用 `py` 命令，则执行：

```bat
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

安装完成后，再双击 `pdf_zip_unpacker.py`。

常见安装失败原因：

- 电脑没有连接网络。
- 公司网络、代理或防火墙阻止访问 Python 软件源。
- Python 版本低于 3.9。
- Python 或 pip 安装损坏。
- 当前 Windows 用户没有安装软件的权限。

## 命令行高级用法

批量扫描脚本所在目录：

```bat
python pdf_zip_unpacker.py
```

批量扫描指定文件夹：

```bat
python pdf_zip_unpacker.py "D:\待处理文件"
```

只处理一个 PDF：

```bat
python pdf_zip_unpacker.py "D:\待处理文件\示例.pdf"
```

设置最大递归层数和每层大小上限：

```bat
python pdf_zip_unpacker.py "D:\待处理文件" --max-depth 200 --max-layer-gb 30
```

可用参数：

```text
--max-depth 100      最大递归层数，默认 100
--max-layer-gb 20    每层允许解压的最大总大小，默认 20 GiB
```

## 常见提示解释

### `File is not a zip file`

表示当前文件不是标准 ZIP。程序还会继续尝试 7z 和 RAR，不会因为这一条提示立即结束。

### `已确认内容是标准 PDF 文档`

表示当前文件是真正的 PDF，不是压缩包，因此无法继续递归解压。例如 `暖父1女儿上学.pdf` 的外层是 ZIP，但里面是一个真正的加密 PDF，所以会在第二层停止。

### `未找到 UnRAR`

表示程序遇到了 RAR，但电脑没有找到 WinRAR 的 `UnRAR.exe`。安装 WinRAR 后重新运行。

### `Permission denied`、`Access is denied` 或“拒绝访问”

把工具和待处理文件移到当前用户可写的目录，例如桌面、文档或 D 盘普通文件夹。不要放在 `C:\Program Files` 或 Windows 系统目录中。

### 没有生成 MP4

可能原因：

- 解出来的是真正 PDF，不是压缩包。
- 五个候选密码都不正确。
- 内部格式不是 ZIP、7z 或 RAR。
- 压缩包损坏。
- 压缩包内部没有 MP4。
- 达到了递归层数或解压大小安全上限。

## 注意事项

- 大型、多层压缩文件需要足够的磁盘空间。
- 程序只清理自己创建的临时内容，不会删除起始 PDF。
- 运行过程中强制关闭 Python，可能导致临时目录来不及清理。
- 只处理来源可信的文件。
