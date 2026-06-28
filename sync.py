import os
import re
from pathlib import Path

from notion_client import Client
from notion_to_md import NotionToMD
import frontmatter

# =====================================================
# ⚠️ 请修改下方配置
# =====================================================

# 你的文章数据库 ID（从 Notion 数据库页面 URL 中提取）
# 例如：https://www.notion.so/username/1234567890abcdef1234567890abcdef?v=...
# 取中间那串 32 位字符：1234567890abcdef1234567890abcdef
DATABASE_ID = os.environ.get("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", "⚠️ 请替换为你的 DATABASE_ID")

# 文章存放的目录（如果不存在会自动创建）
OUTPUT_DIR = "posts"

# Notion 数据库中的属性名称映射（改为你实际使用的名称）
PROP_TITLE = "爱玩win11的me"          # ⚠️ 改为你数据库中“标题”列的名字
PROP_TAGS = ""           # ⚠️ 改为你数据库中“标签”列的名字（没有可忽略）
PROP_STATUS = "published"         # ⚠️ 改为你数据库中“状态”列的名字（用于过滤草稿）
PUBLISHED_STATUS = "已发布"   # ⚠️ 只有状态等于这个值的文章才会被导出

# =====================================================
# 以下代码无需修改
# =====================================================

# 初始化 Notion 客户端
NOTION_KEY = os.environ.get("NOTION_KEY")
if not NOTION_KEY:
    raise ValueError("❌ 错误：未找到 NOTION_KEY 环境变量，请在 GitHub Secrets 中配置")

client = Client(auth=NOTION_KEY)

# 创建输出目录
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# 初始化转换器（将 Notion 块转为 Markdown）
md_converter = NotionToMD(client)


def clean_filename(title: str) -> str:
    """将文章标题转为安全的文件名"""
    # 移除非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '', title)
    # 限制长度
    if len(filename) > 50:
        filename = filename[:50]
    return filename.strip() or "untitled"


def get_page_property(page, prop_name: str):
    """安全获取页面属性值"""
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


def convert_blocks_to_md(page_id: str) -> str:
    """将 Notion 页面所有块转换为 Markdown 文本"""
    try:
        # 获取页面的所有子块
        blocks = client.blocks.children.list(block_id=page_id)
        # 使用 notion-to-md 转换
        markdown = md_converter.blocks_to_md(blocks.get("results", []))
        return str(markdown) if markdown else ""
    except Exception as e:
        print(f"  ⚠️ 转换块时出错: {e}")
        return ""


def main():
    print("🚀 开始同步 Notion 文章...")
    
    # 查询数据库中的所有页面
    try:
        response = client.databases.query(
            database_id=DATABASE_ID,
            # ⚠️ 可选：如果你想按创建时间排序，取消下面的注释
            # sorts=[{"timestamp": "created_time", "direction": "descending"}]
        )
    except Exception as e:
        print(f"❌ 查询数据库失败，请检查 DATABASE_ID 是否正确: {e}")
        return
    
    pages = response.get("results", [])
    print(f"📊 找到 {len(pages)} 个页面")
    
    success_count = 0
    skip_count = 0
    
    for page in pages:
        page_id = page["id"]
        
        # 获取标题
        title = get_page_property(page, PROP_TITLE)
        if not title:
            print(f"  ⚠️ 跳过无标题页面: {page_id}")
            skip_count += 1
            continue
        
        # 检查状态（如果配置了状态过滤）
        if PROP_STATUS and PUBLISHED_STATUS:
            status = get_page_property(page, PROP_STATUS)
            if status != PUBLISHED_STATUS:
                print(f"  ⏭️ 跳过 {title}（状态: {status}）")
                skip_count += 1
                continue
        
        print(f"  📝 处理: {title}")
        
        # 转换内容为 Markdown
        content = convert_blocks_to_md(page_id)
        
        # 获取标签
        tags = get_page_property(page, PROP_TAGS)
        if tags and isinstance(tags, list):
            tags = [t for t in tags if t]  # 过滤空标签
        else:
            tags = []
        
        # 构建 frontmatter（文章元数据）
        post = frontmatter.Post(
            content,
            title=title,
            date=page.get("created_time", ""),
            updated=page.get("last_edited_time", ""),
            tags=tags,
            # 可以添加更多属性，例如：
            # url=page.get("url", ""),
        )
        
        # 生成安全的文件名
        filename = clean_filename(title)
        filepath = Path(OUTPUT_DIR) / f"{filename}.md"
        
        # 防止重名
        counter = 1
        while filepath.exists():
            filepath = Path(OUTPUT_DIR) / f"{filename}_{counter}.md"
            counter += 1
        
        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        
        success_count += 1
        print(f"  ✅ 已保存: {filepath}")
    
    print(f"\n🎉 同步完成！成功: {success_count} 篇，跳过: {skip_count} 篇")


if __name__ == "__main__":
    main()
