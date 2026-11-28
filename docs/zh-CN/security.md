# 安全与隐私

[English](../security.md) · [繁體中文](../zh-TW/security.md) · **简体中文**

## 安全与隐私

- 在暴露服务之前完成首次运行设置。在没有任何账户时，
  `/api/v1/auth/setup` 按设计是公开的；在创建 root 账户之前，不要
  让全新实例可通过 tunnel 访问。
- 一个 root 加上普通账户保护档案。密码使用 Argon2 哈希；会话令牌在
  `user_session` 中只存储为 SHA-256 哈希。cookie 是 HttpOnly、
  SameSite=Lax，并在 `APSOR_COOKIE_SECURE=true` 时启用 Secure。
  临时密码只返回一次，从不记录或缓存，账户必须在加载内容之前更改它。
- 每条私有行都携带 `user_id`；复合外键把谱系限制在一个账户内，
  `apsor_app` 上的 PostgreSQL 强制行级安全会拒绝跨账户读写，即使
  缺少服务过滤条件。仅 root 的路由守卫保护账户和全局设置，但 root
  不是数据超级用户，无法通过普通 API 查询读取另一个账户的档案。
  root 密码重置和显式模拟是刻意的受信任恢复能力，可以把登录访问权
  转移给目标账户；停止模拟需要 root 密码、删除该会话并签发新的 root
  会话。请把 root 视为最高信任凭据，不要把 RLS 当作针对恶意 root
  的保护。
- **伙伴管理是明文规定的例外。** 在 `/api/v1/admin/companions` 下，root
  的请求会另外设置事务范围内的 `app.admin_scope = 'companion'`。数据库策略
  因此允许 root 跨账号读取与管理伙伴相关数据：伙伴选择与策略、故事进度
  （羁绊与已讲过的记忆）、root 的人格与记忆覆盖设置、生活故事任务，以及
  **生活故事的全文**——这些故事取材自该账号自己的记忆。此范围永远不会触及
  档案馆本身（`file`、`memory`、`chunk`、对话），除 root 之外的角色一律拒绝，
  在模拟会话中也不适用。每次阅读生活故事全文、每次对账号伙伴的更改，
  都会追加到 `companion_admin_access_log`（root 只能新增与读取，任何人都
  无法修改或删除），而故事列表永远不含正文。账号的伙伴页面会明确告知
  管理员可以阅读这些故事。
- **RLS 是应用边界，而不是主机边界。** 部署登录是用于迁移和维护的
  PostgreSQL 超级用户；应用会为请求事务切换到 `apsor_app`。任何
  本地操作系统用户、数据库/缓存网络上的任何容器，或任何能读取
  `.secrets/`/`.env` 的人，都可以绕过 API 和 RLS。请保持主机可信，
  把数据库和缓存绑定到 localhost 或内部网络，使用不同的主机账户，
  为任何共享主机设置强数据库/缓存密码，并在暴露后轮换凭据。未来的
  加固步骤是专用的非超级用户运行时登录加上单独的维护凭据。
- 生产 Compose 文件不发布任何主机端口；Cloudflare Tunnel 连接到 Caddy，
  Caddy 再连接到 API。登录限流在内存中，因此是单进程的；请运行一个
  API 进程，或在横向扩展前把限流迁移到 Valkey。
- 路径会拒绝遍历段、反斜杠、控制字符和过长的值。上传限制为 10 MB，
  并受扩展名允许列表限制。
- 来自文件和记忆的 HTML 通过 React 作为文本渲染。Agent Markdown
  使用 `skipHtml`；DOCX 预览在禁用脚本的沙箱中运行，PPTX 幻灯片则绘制到本地
canvas。UI 从不使用
  `dangerouslySetInnerHTML`。
- DeepSeek 密钥位于 `.secrets/deepseek.env` 或环境中。它永远不会被
  记录、返回或提交。从设置页面保存的密钥在 PostgreSQL 中加密，并且
  只作为四字符提示返回。
- 对象存储凭据位于被 gitignore 的 `.secrets/r2.env` 或 `.secrets/s3.env`
  （随附的 RustFS 另有 `secrets/` 下的 Docker secret 文件），以只读方式挂载，
  永远不会成为容器环境变量。存储桶是私有的，没有预签名或公开 URL。
- 摘要和 agent 轮次会发生 AI 调用。如果提供商失败，API 会返回稳定
  的错误，而不是编造答案。
