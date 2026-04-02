# nova-frontmatter

nova-frontmatter 是一个用 Go 编写的命令行工具，用于操作 Markdown 文件的 frontmatter。

目前提供以下命令：

## replace

替换 frontmatter 中的值：

```bash
nova-frontmatter replace --path "/plan_state" --value "done" --type "string" XXX.md --create-missing
```

参数说明：

- `--path`：JSON Pointer（RFC 6901）路径，将 frontmatter 视为 JSON 结构进行寻址
- `--value`：目标值
- `--type`：值的类型，支持 `string|number|boolean|null|json|array`，用于解析 `--value`
- `--create-missing`：字段不存在时自动创建，包括中间路径

省略 `--type` 时自动推断：

```
"done"  → string "done"
"3"     → number 3
"true"  → boolean true
"null"  → null
```

## remove / add

与 replace 同类的操作命令。

## get

获取 frontmatter 中的值，返回 JSON：

```bash
nova-frontmatter get --path "/plan_state" [--output text|json|yaml] XXX.md
```
