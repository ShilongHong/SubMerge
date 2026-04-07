# SubMerge - Clash 订阅合成工具

支持将多个订阅源智能合并，生成永久订阅链接。

## 🚀 快速开始

### 方式一：直接运行（推荐开发使用）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行服务
python app.py

# 3. 打开浏览器
访问 http://127.0.0.1:5000
```

### 方式二：打包为EXE（推荐分发使用）

```bash
# 1. 安装PyInstaller
pip install pyinstaller

# 2. 打包成单个exe文件
pyinstaller build.spec

# 3. 运行生成的exe
双击运行 dist/SubMerge.exe

# 4. 打开浏览器
访问 http://127.0.0.1:5000
```

**注意事项：**
- 打包后的exe文件位于 `dist/` 目录
- 首次运行时会自动创建 `configs/`、`uploaded_files/`、`subscription_cache/` 等必要目录
- exe文件可独立运行，无需Python环境

## 📖 使用步骤

### 创建新订阅

1. **留空Token** - 系统自动生成新Token
2. **添加订阅源** - 点击"➕ 添加订阅"按钮
3. **填写信息**：
   - 订阅名称：用于标识节点来源
   - 订阅来源：选择"远程链接"或"本地文件"
   - 是否主订阅：勾选后使用该订阅的规则配置
   - 参与规则：勾选后节点会出现在规则代理组中
4. **生成链接** - 点击"🔥 生成订阅链接"
5. **复制链接** - 将生成的链接添加到Clash客户端

### 更新已有订阅

1. **输入Token** - 在Token输入框填入之前保存的Token
2. **加载配置** - 点击"📥 加载配置"按钮
3. **修改配置** - 添加、删除或修改订阅
4. **提交更新** - 点击"🔥 生成订阅链接"（订阅链接不变）

## 🎯 核心功能

- ✅ **支持多个订阅** - 不限制订阅数量
- ✅ **远程/本地双模式** - 支持URL链接和本地文件上传
- ✅ **配置持久化** - Token永久有效，随时更新配置
- ✅ **智能合并** - 主订阅提供规则，其他订阅提供节点
- ✅ **节点分组** - 自动创建ALL组、订阅组、其他节点组
- ✅ **规则控制** - 可选择订阅是否参与规则代理组

## 📝 配置说明

### 主订阅
- 提供规则（rules）和代理组结构（proxy-groups）
- 必须选择一个订阅作为主订阅

### 参与规则
- **勾选**：该订阅的节点会出现在所有规则代理组中（PROXY、YouTube等）
- **不勾选**：节点仅出现在独立的订阅组和ALL组中

### 代理组结构
```yaml
proxy-groups:
  - name: ALL          # 包含所有订阅的所有节点
  - name: 订阅1        # 只包含订阅1的节点
  - name: 订阅2        # 只包含订阅2的节点
  - name: 其他节点     # 包含除主订阅外的所有节点
  - name: PROXY       # 原有规则代理组（包含参与规则的节点）
```

## 🔧 API接口

### 创建配置
```bash
POST /api/create
Content-Type: multipart/form-data

参数：
- sub_name_0, sub_name_1...: 订阅名称
- sub_url_0, sub_url_1...: 订阅URL（远程模式）
- sub_file_0, sub_file_1...: 订阅文件（本地模式）
- is_main_0, is_main_1...: 是否主订阅（true/false）
- in_rules_0, in_rules_1...: 是否参与规则（true/false）
- token: 已有Token（可选，用于更新）

返回：
{
  "success": true,
  "token": "生成的Token",
  "subscribe_url": "订阅链接"
}
```

### 查询配置
```bash
GET /api/config/<token>
```

### 更新配置
```bash
PUT /api/config/<token>
```

### 获取订阅
```bash
GET /api/subscribe?token=<token>
返回：Clash YAML配置文件
```

## 📂 数据文件

- `configs/` - 配置存储目录
  - 每个Token对应一个独立的JSON文件
  - 文件格式：`{token}.json`
- 可直接删除文件来移除配置
- 备份整个`configs/`目录即可

## ⚠️ 注意事项

1. **Token管理** - 请妥善保管Token，丢失后无法恢复配置
2. **主订阅** - 必须有一个主订阅，提供规则和代理组结构
3. **文件上传** - 支持.yaml、.yml、.txt格式，自动识别base64编码
4. **节点重名** - 自动处理，添加数字后缀（如HK_1、HK_2）

## 📄 许可证

MIT License
