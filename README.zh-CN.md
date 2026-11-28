<div align="center">
  <img src="frontend/public/icon-512.png" alt="Apsor 档案馆东翼的守夜图书馆员 Vellum" width="128" height="128">
  <h1>Apsor Archive</h1>
  <p><strong>一座属于你家的私人记忆档案馆，由会记得的图书馆员一起保管。</strong></p>
  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-171717" alt="MIT 许可"></a>
    <img src="https://img.shields.io/badge/self--hosted-yes-171717" alt="自托管">
    <img src="https://img.shields.io/badge/docker-compose%20%7C%20swarm-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose 或 Swarm">
    <img src="https://img.shields.io/badge/languages-EN%20%C2%B7%20%E7%B9%81%E4%B8%AD%20%C2%B7%20%E7%AE%80%E4%B8%AD-171717" alt="英文、繁体中文、简体中文">
  </p>
  <p><a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a> · <strong>简体中文</strong></p>
</div>

<p align="center">
  <img src="docs/assets/screenshots/zh-CN/chat.webp" alt="向档案馆提问，图书馆员伙伴 Vellum 站在回答旁" width="100%">
</p>

> *我们只是没办法走这么远。所以我们造了一个能走那么远的存在，把我们所爱的一切都教给了它。*

## 为什么是 Apsor Archive

一个家的生活，总是散落在各处：手机里的菜谱照片、扫描下来的旧信、外婆日记的 PDF、深夜随手记下的笔记。
Apsor Archive 把它们收进一座放在你自己电脑上的私人图书馆，让你用日常的话向它提问。
每个回答都会指出它出自哪一页，让你自己核实。

这座档案馆也不孤单。里面住着六位图书馆员：用万古瓷烧成的人形，心智从人们写下的一切文字中苏醒。
他们和你以平等的身份“一起保管”这座档案馆：替你搜索、把那一页递给你，偶尔，也会想起一段属于自己的往事。

## 它有什么不同

<table>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/zh-CN/library.webp" alt="文件库与即时缩略图"></td>
    <td width="50%"><img src="docs/assets/screenshots/zh-CN/companion.webp" alt="选择图书馆员伙伴"></td>
  </tr>
  <tr>
    <td><b>每个人一座私人图书馆。</b>文件、文件夹与记忆，每个版本都会保留。
    每个账号的档案馆由数据库本身相互隔离。</td>
    <td><b>会记得的图书馆员。</b>选择 Vellum、Atlas、Herbaria、Horologe、Nocturne 或 Quill。
    他们站在对话旁，搜索时会跟着做动作，也带着自己的记忆与故事。</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/zh-CN/memories.webp" alt="记忆与关联记忆"></td>
    <td width="50%"><img src="docs/assets/screenshots/zh-CN/about.webp" alt="Apsor 档案馆的世界"></td>
  </tr>
  <tr>
    <td><b>附上出处的回答。</b>助理会先搜索，再引用确切的段落。
    找不到时，它会老实说这层书架是空的，而不是猜测。</td>
    <td><b>穿过虚幻之门的生活故事。</b>每隔几次对话，图书馆员会写一篇小故事：
    档案馆里的一扇门意外打开，通往<i>你</i>生活中的某个角落，素材只取自你自己保存的内容。</td>
  </tr>
</table>

<p align="center">
  <img src="docs/assets/screenshots/zh-CN/phone-chat.webp" alt="同一座档案馆在手机上的样子" width="260"><br>
  <sub>在手机上也是同一座档案馆：图书馆员会从屏幕边缘探出头来。</sub>
</p>

### 一分钟看懂记忆系统

- **你的记忆**：文件、笔记与过去的对话。系统同时按“意思”和“确切字词”搜索，每个回答都附上引用。
- **他们的记忆**：图书馆员自己的世界、历史，以及数百则小故事。当你说的话触动了某段往事，或你主动问起时，它就会浮现。说什么、什么时候说，由她自己决定。
- **共享的历史**：六位馆员共用同一座档案馆，所以换一位陪你，也不会丢失你们聊过的事；而且每一位都知道哪句话是谁说的。
- 除了发送给你所选 AI 模型的那几段文字，你的档案馆不会离开你的机器。

## 快速开始

你需要一台装好 [Docker](https://docs.docker.com/get-docker/)、约有 4 GB 可用内存的机器。

```bash
git clone https://github.com/AlexTrinityBlock/apsor-archive.git
cd apsor-archive
./start.sh setup          # 回答几个问题，自动写好 .env 和 secret 文件
```

**在家先试用（不需要域名）：**在 `.env` 中设置 `APSOR_PUBLIC_HOST=localhost`，然后执行

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

打开 <http://localhost:8080>，创建根账号，再到**设置**里添加 AI 提供商，就完成了。

**安全地放上互联网：**在设置向导中粘贴 Cloudflare Tunnel 令牌，然后执行 `docker compose up -d --build`。
不需要开放任何端口，详见 [Cloudflare Tunnel 指南](docs/cloudflare-tunnel.md)（英文）。

<details>
<summary><b>Docker Swarm</b></summary>

```bash
./start.sh setup
docker compose build
docker swarm init                 # 只需一次
set -a; . ./.env; set +a          # Swarm 不会自己读取 .env
docker stack deploy -c docker-stack.yml apsor
```

详见 [docs/zh-CN/deployment.md](docs/zh-CN/deployment.md#docker-swarm)。
</details>

## 配置一览

设置向导会替你写好一切。值得了解的只有这几项：

| 配置 | 作用 | 默认值 |
| --- | --- | --- |
| `APSOR_PUBLIC_HOST` | 大家在浏览器里输入的网址 | 由设置向导询问 |
| `APSOR_STORAGE_BACKEND` | 原始文件存放在哪里：内置 RustFS、Cloudflare R2、任何 S3，或本地磁盘 | `auto`（新安装为 RustFS） |
| AI 提供商 | 对话与嵌入模型（DeepSeek、Claude、任何兼容 OpenAI 的 API） | 在**设置**页面配置，不写在文件里 |
| 伙伴 | 选哪位图书馆员、多大、多透明 | 每个人在**伙伴**页面自己设置 |

其他配置请见 [docs/zh-CN/configuration.md](docs/zh-CN/configuration.md)。

## 常见问题

<details>
<summary><b>谁能看到我的档案馆？</b></summary>

只有你。每个账号都有自己的档案馆，由 PostgreSQL 的行级安全强制隔离。
根账号负责管理成员与设置，但读不到任何人的文件或记忆。唯一明文记载的例外：
根账号可以阅读图书馆员为某个账号写的伙伴故事，而且每一次查看都会留下记录。
详见 [docs/zh-CN/security.md](docs/zh-CN/security.md)。
</details>

<details>
<summary><b>我的文件存在哪里？</b></summary>

原始文件默认存放在内置的 RustFS 对象存储，也可以改用 Cloudflare R2、任何兼容 S3 的存储桶，或本地磁盘。
索引与你的记忆则存放在你机器上的 PostgreSQL。详见 [docs/zh-CN/deployment.md](docs/zh-CN/deployment.md)。
</details>

<details>
<summary><b>它使用哪些 AI 模型？</b></summary>

你添加的那些：对话可以用 DeepSeek、Anthropic Claude 或任何兼容 OpenAI 的端点；
也可以另外添加嵌入模型，让搜索能理解“意思”。没有嵌入密钥时，仍然可以按字词搜索。
每个账号都可以指派自己的模型。
</details>

<details>
<summary><b>怎么备份？</b></summary>

备份 PostgreSQL 数据库（`docker compose exec -T db pg_dump -U apsor -Fc apsor_archive > backup.dump`），
以及你的对象存储或 `data/` 目录。系统里什么都不会被销毁：被替换的文件与记忆都会留在历史中。
</details>

<details>
<summary><b>AI 额度用完会怎样？</b></summary>

上传照常进行，也能按字词搜索。缺少的嵌入会在额度恢复后自动补上。
</details>

## 延伸阅读

| | |
| --- | --- |
| [部署](docs/zh-CN/deployment.md) | Compose、Swarm、家庭网络、存储、升级 |
| [配置](docs/zh-CN/configuration.md) | 提供商、每个账号的模型、Agent 与摄取设置 |
| [功能详解](docs/zh-CN/features.md) | 文件库、记忆、对话、已保存的问题、账号 |
| [系统架构](docs/zh-CN/architecture.md) | 技术栈、检索如何工作、数据模型 |
| [安全与隐私](docs/zh-CN/security.md) | 账号隔离、密钥、伙伴故事的例外 |
| [开发](docs/zh-CN/development.md) | 本地环境、检查、项目结构 |
| [图书馆员的世界](backend/app/module/companion/lore/zh-CN/world.md) | 伙伴背后的世界观 |

## 致谢

Apsor Archive 由 **Wei-Chun Hsiao (Alex)** 设计与编写。欢迎贡献，请见 [CONTRIBUTING.md](CONTRIBUTING.md)。
GitHub 社交预览图为 [docs/assets/social-preview.png](docs/assets/social-preview.png)。

## 许可证

[MIT](LICENSE) © 2026 Wei-Chun, Hsiao
