# GitLab 群组和项目迁移工具

这是一个用于将GitLab实例中的群组和项目按照1:1的路径迁移到目标GitLab实例的Python工具。

## 功能特点

- 支持将源GitLab实例中的群组及其子群组结构完整迁移
- 支持群组内的所有项目迁移，包括项目数据、代码和配置
- 保持源群组和项目的路径结构不变
- 提供详细的日志记录，便于跟踪迁移过程
- 支持处理嵌套的子群组结构

## 创建虚拟环境

强烈建议在虚拟环境中运行本工具，以避免依赖冲突：

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
.\venv\Scripts\Activate.ps1

# 激活虚拟环境 (Linux/Mac)
source venv/bin/activate
```

## 安装依赖

在激活的虚拟环境中安装必要的依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

### 前提条件

1. 确保在源GitLab实例中拥有**API访问令牌**，并且该令牌具有足够的权限（至少需要`api`和`read_repository`权限）
2. 确保在目标GitLab实例中拥有**API访问令牌**，并且该令牌具有足够的权限（至少需要`api`和`write_repository`权限）
3. 确保源群组路径正确无误

### 使用方法

```bash
python gitlab_migration.py --source-url <源GitLab URL> --source-token <源访问令牌> \
                           --target-url <目标GitLab URL> --target-token <目标访问令牌> \
                           --source-group <源群组路径> [--max-workers <并发数>] [--overwrite]
```

### 可选参数

- `--timeout <秒数>`: 设置API请求超时时间，默认为30秒
- `--verify-ssl <true|false>`: 是否验证SSL证书，默认为true
- `--max-workers <并发数>`: 并发迁移的最大工作线程数，默认5。可以根据GitLab服务器性能调整此值，提高迁移速度
- `--overwrite`: 是否覆盖已存在的项目，默认不覆盖（添加此参数表示覆盖）

### 功能说明

- **智能覆盖控制**：默认不会覆盖目标GitLab中已存在的项目，可通过`--overwrite`参数启用覆盖功能
- **并发迁移**：支持多项目并行迁移，大幅提高迁移速度
- **递归处理子群组**：自动处理群组下的所有子群组和项目

## 示例

```bash
python gitlab_migration.py --source-url https://gitlab.example.com \
                          --source-token syt_xxxxxxxxxxxxxxxxxxxx \
                          --target-url https://gitlab.new-example.com \
                          --target-token syt_yyyyyyyyyyyyyyyyyyyy \
                          --source-group my-group/subgroup
```

## 迁移过程说明

1. 脚本首先连接到源GitLab和目标GitLab实例，验证访问令牌的有效性
2. 获取源群组的信息
3. 在目标GitLab中创建相同路径结构的群组
4. 逐个导出源群组中的项目并导入到目标群组
5. 递归处理子群组

## 注意事项

1. 迁移过程中请保持网络连接稳定
2. 对于大型项目，迁移可能需要较长时间
3. 某些特定的项目配置（如集成、Webhook等）可能需要手动重新配置
4. 建议在正式迁移前先在测试环境进行验证
5. 请确保目标GitLab实例有足够的存储空间

## 日志记录

脚本会同时将日志输出到控制台和`gitlab_migration.log`文件中，包括：

- 迁移开始和结束的时间
- 每个群组和项目的迁移状态
- 错误信息和失败原因

## 故障排除

### 常见错误

1. **认证失败**：请检查访问令牌是否正确，以及是否具有足够的权限
2. **SSL验证错误**：如果目标GitLab使用自签名证书，可以使用`--verify-ssl false`参数
3. **导出/导入超时**：对于大型项目，可以尝试增加`--timeout`参数的值
4. **项目冲突**：如果目标群组中已存在同名项目，迁移将会失败

### 获取帮助

如果遇到其他问题，请查看日志文件获取详细信息，或检查GitLab实例的API状态。

## 版本历史

### 1.0.0

- 初始版本
- 支持群组和项目的完整迁移
- 支持嵌套子群组
- 详细的日志记录

## 许可证

本项目采用MIT许可证 - 详情请查看LICENSE文件