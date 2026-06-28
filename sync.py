import os
import re
from pathlib import Path

from notion_client import Client
import frontmatter

# =====================================================
# ⚠️ 请修改下方配置（和之前一样）
# =====================================================

DATABASE_ID = os.environ.get("NOTION_DB", "⚠️ 请替换为你的 DATABASE_ID")
OUTPUT_DIR = "posts"

PROP_TITLE = "爱玩win11的me"          # ⚠️ 改为你数据库中的“标题”列名
PROP_TAGS = ""           # ⚠️ 改为你数据库中的“标签”列名
PROP_STATUS = "published"         # ⚠️ 改为你数据库中的“状态”列名
PUBLISHED_STATUS = "已发布"   # ⚠️ 只有状态等于这个值的文章才会导出

# =====================================================
# 以下为自定义 Markdown 转换函数（无需额外库）
# =====================================================

NOTION_KEY = os.environ.get("NOTION_KEY")
if not NOTION_KEY:
    raise ValueError("❌ 未找到 NOTION_KEY 环境变量")

client = Client(auth=NOTION_KEY)
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def get_page_property(page, prop_name: str):
    """安全获取属性值（和之前一样）"""
    props = page.get("properties", {})
    if prop_name not in props:
        return None
    prop = props[prop_name]
    prop_type = prop.get("type")
    if prop_type == "title":
        return prop.get("title", [{}])[0].get("plain_text", "") if prop.get("title") else ""
    elif prop_type == "rich_text":
        return prop.get("rich_text", [{}])[0].get("plain_text", "") if prop.get("rich_text") else ""
    elif prop_type == "select":
        return prop.get("select", {}).get("name", "") if prop.get("select") else ""
    elif prop_type == "multi_select":
        return [item.get("name", "") for item in prop.get("multi_select", [])]
    elif prop_type == "date":
        date_data = prop.get("date", {})
        return date_data.get("start", "") if date_data else ""
    return None


def clean_filename(title: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '', title)
    return (filename[:50] or "untitled").strip()


def block_to_markdown(block):
    """将单个 Notion 块转为 Markdown 字符串"""
    block_type = block.get("type")
    if not block_type:
        return ""

    # 通用获取富文本
    def get_rich_text(prop_name):
        rich_text = block.get(block_type, {}).get(prop_name, [])
        return "".join([t.get("plain_text", "") for t in rich_text])

    # 处理各种块类型
    if block_type == "paragraph":
        return get_rich_text("rich_text") + "\n\n"
    elif block_type == "heading_1":
        return "# " + get_rich_text("rich_text") + "\n\n"
    elif block_type == "heading_2":
        return "## " + get_rich_text("rich_text") + "\n\n"
    elif block_type == "heading_3":
        return "### " + get_rich_text("rich_text") + "\n\n"
    elif block_type == "bulleted_list_item":
        return "- " + get_rich_text("rich_text") + "\n"
    elif block_type == "numbered_list_item":
        # 注意：真实编号由顺序决定，这里简单用 "1. "
        return "1. " + get_rich_text("rich_text") + "\n"
    elif block_type == "to_do":
        checked = block.get("to_do", {}).get("checked", False)
        mark = "[x]" if checked else "[ ]"
        return "- " + mark + " " + get_rich_text("rich_text") + "\n"
    elif block_type == "code":
        code = block.get("code", {})
        lang = code.get("language", "")
        text = "".join([t.get("plain_text", "") for t in code.get("rich_text", [])])
        return f"```{lang}\n{text}\n```\n\n"
    elif block_type == "quote":
        return "> " + get_rich_text("rich_text") + "\n\n"
    elif block_type == "callout":
        # 简单处理，把 icon 和 text 一起输出
        icon = block.get("callout", {}).get("icon", {}).get("emoji", "")
        text = get_rich_text("rich_text")
        return f"{icon} {text}\n\n"
    elif block_type == "divider":
        return "---\n\n"
    elif block_type == "image":
        # 只处理外部图片，提取 URL
        img = block.get("image", {})
        url = img.get("external", {}).get("url") or img.get("file", {}).get("url")
        return f"![]({url})\n\n" if url else ""
    else:
        # 其他类型（如 bookmark、embed 等）忽略或简单处理
        return ""


def convert_blocks_to_md(page_id: str) -> str:
    """递归获取所有子块并转换为 Markdown"""
    try:
        blocks = client.blocks.children.list(block_id=page_id).get("results", [])
        markdown = ""
        for block in blocks:
            markdown += block_to_markdown(block)
            # 如果有子块（如 toggle、synced_block 等），递归
            if block.get("has_children", False):
                markdown += convert_blocks_to_md(block["id"])
        return markdown
    except Exception as e:
        print(f"  ⚠️ 转换块时出错: {e}")
        return ""


def main():
    print("🚀 开始同步 Notion 文章...")
    try:
        response = client.databases.query(database_id=DATABASE_ID)
    except Exception as e:
        print(f"❌ 查询数据库失败: {e}")
        return

    pages = response.get("results", [])
    print(f"📊 找到 {len(pages)} 个页面")

    success_count = 0
    skip_count = 0

    for page in pages:
        page_id = page["id"]
        title = get_page_property(page, PROP_TITLE)
        if not title:
            print(f"  ⚠️ 跳过无标题页面: {page_id}")
            skip_count += 1
            continue

        # 状态过滤
        if PROP_STATUS and PUBLISHED_STATUS:
            status = get_page_property(page, PROP_STATUS)
            if status != PUBLISHED_STATUS:
                print(f"  ⏭️ 跳过 {title}（状态: {status}）")
                skip_count += 1
                continue

        print(f"  📝 处理: {title}")
        content = convert_blocks_to_md(page_id)

        tags = get_page_property(page, PROP_TAGS)
        if tags and isinstance(tags, list):
            tags = [t for t in tags if t]
        else:
            tags = []

        post = frontmatter.Post(
            content,
            title=title,
            date=page.get("created_time", ""),
            updated=page.get("last_edited_time", ""),
            tags=tags,
        )

        filename = clean_filename(title)
        filepath = Path(OUTPUT_DIR) / f"{filename}.md"
        counter = 1
        while filepath.exists():
            filepath = Path(OUTPUT_DIR) / f"{filename}_{counter}.md"
            counter += 1

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

        success_count += 1
        print(f"  ✅ 已保存: {filepath}")

    print(f"\n🎉 同步完成！成功: {success_count} 篇，跳过: {skip_count} 篇")


if __name__ == "__main__":
    main()
