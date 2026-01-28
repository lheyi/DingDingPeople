import os
import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import json
import re
from datetime import datetime, timedelta

# 从环境变量获取配置
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
SECRET = os.environ.get('SECRET')

# --- 模块化内容生成系统 ---

class ContentProvider:
    """内容生成基类，用于扩展不同类型的消息源"""
    def generate(self, task):
        raise NotImplementedError("Subclasses must implement generate()")

class StaticContentProvider(ContentProvider):
    """静态文本内容"""
    def generate(self, task):
        return task.get('content', '无内容')

class CrawlerContentProvider(ContentProvider):
    """
    【扩展示例】爬虫内容提供者
    在此处编写爬虫逻辑，例如爬取新闻、天气、股票等
    """
    def generate(self, task):
        source_url = task.get('source_url', '未知来源')
        # 示例逻辑：实际使用时可以使用 requests.get(source_url)
        return f"🚀 动态数据获取中...\n来源: {source_url}\n(在此处编写您的爬虫代码)"

# 注册内容提供者
# 如果需要新增功能，只需新建一个类继承 ContentProvider，并在此处注册
PROVIDERS = {
    'static': StaticContentProvider(),
    'crawler': CrawlerContentProvider(),
    # 'weather': WeatherProvider(),  <-- 示例：新增天气模块
    # 'stock': StockProvider(),      <-- 示例：新增股票模块
}

def get_task_content(task):
    """根据 content_type 分发到对应的 Provider"""
    c_type = task.get('content_type', 'static')
    provider = PROVIDERS.get(c_type)
    if provider:
        try:
            return provider.generate(task)
        except Exception as e:
            return f"❌ 内容生成失败: {str(e)}"
    return f"⚠️ 未知的任务类型: {c_type}"

# --- 核心工具函数 ---

def derive_title(md_text):
    """从 Markdown 内容中提取标题"""
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith('#'):
            return s.lstrip('#').strip()
    return '提醒通知'

def get_beijing_time():
    """获取北京时间 (UTC+8)"""
    return datetime.utcnow() + timedelta(hours=8)

def format_message(title, content):
    """默认消息模板"""
    now = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
    template = """### 📌 任务提醒：{title}

---
**📅 发送时间：** {datetime}

**💬 提醒内容：**
> {content}

---
#### 📋 任务状态
* **执行节点：** GitHub Actions
* **发送渠道：** 钉钉自动化助手
* **安全策略：** HMAC-SHA256
"""
    return template.format(title=title, datetime=now, content=content)

def get_signed_url():
    """生成钉钉带签名的 Webhook URL"""
    if not SECRET or not WEBHOOK_URL:
        print("错误: 缺少 WEBHOOK_URL 或 SECRET 环境变量")
        return None
        
    timestamp = str(round(time.time() * 1000))
    secret_enc = SECRET.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, SECRET)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))
    
    if '?' in WEBHOOK_URL:
        return f"{WEBHOOK_URL}&timestamp={timestamp}&sign={sign}"
    return f"{WEBHOOK_URL}?timestamp={timestamp}&sign={sign}"

def send_markdown_msg(markdown_text, at_mobiles=[], at_user_ids=[], is_at_all=False):
    """发送 Markdown 消息"""
    url = get_signed_url()
    if not url:
        return

    headers = {"Content-Type": "application/json"}
    title = derive_title(markdown_text)
    
    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown_text
        },
        "at": {
            "isAtAll": is_at_all,
            "atUserIds": at_user_ids,
            "atMobiles": at_mobiles
        }
    }
    
    try:
        res = requests.post(url, json=data, headers=headers)
        print(f"发送响应: {res.text}")
    except Exception as e:
        print(f"发送失败: {e}")

# --- 调度逻辑 ---

def run_scheduler():
    now = get_beijing_time()
    today_str = now.strftime('%Y-%m-%d')
    current_hm = now.strftime('%H:%M')
    
    print(f"当前系统时间(北京时间): {today_str} {current_hm}")

    # 读取任务
    try:
        with open('tasks.json', 'r', encoding='utf-8') as f:
            # 移除注释支持 JSON5 风格
            text = f.read()
            text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
            tasks = json.loads(text)
    except Exception as e:
        print(f"读取 tasks.json 失败: {e}")
        return

    found_task = False
    
    # 设定时间匹配窗口（分钟）
    # 意味着：只要当前时间在 任务时间 的 15分钟后以内，就视为匹配
    # 配合 GitHub Actions 的 cron 设置（例如每15分钟运行一次），可以确保任务不丢失
    TIME_WINDOW_MINUTES = 15

    for task in tasks:
        # 1. 检查日期
        if task.get('date') != today_str:
            continue
            
        # 2. 检查时间（支持时间窗口匹配）
        task_time_str = task.get('time')
        if task_time_str:
            try:
                # 构造任务的完整 datetime 对象
                task_dt = datetime.strptime(f"{today_str} {task_time_str}", "%Y-%m-%d %H:%M")
                # 计算时间差：当前时间 - 任务时间
                diff = now - task_dt
                diff_minutes = diff.total_seconds() / 60
                
                # 逻辑：
                # 如果 diff_minutes < 0: 任务在未来，还没到时间 -> 跳过
                # 如果 0 <= diff_minutes <= 15: 任务刚刚过去 15 分钟内 -> 发送
                # 如果 diff_minutes > 15: 任务已经过去很久了 -> 跳过 (避免重复发送旧任务)
                
                if diff_minutes < 0:
                    # print(f"任务 {task_time_str} 尚未到时间 (还有 {abs(diff_minutes):.1f} 分钟)")
                    continue
                elif diff_minutes > TIME_WINDOW_MINUTES:
                    # print(f"任务 {task_time_str} 已过期 (超过 {diff_minutes:.1f} 分钟)")
                    continue
                else:
                    print(f">>> 命中时间窗口: 任务设定 {task_time_str}, 当前 {current_hm}, 偏差 {diff_minutes:.1f} 分钟")
            except ValueError:
                print(f"时间格式错误: {task_time_str}，应为 HH:MM")
                continue

        # 3. 生成内容
        print(f"准备发送任务: {task.get('content', '动态内容')[:20]}...")
        final_content = get_task_content(task)
        title = task.get('title', '日程提醒')

        # 4. 处理 @提及
        at_mobiles = task.get('at_mobiles', [])
        is_at_all = task.get('is_at_all', False)
        if is_at_all:
            mentions_text = "@所有人"
        elif at_mobiles:
            mentions_text = ' '.join([f"@{m}" for m in at_mobiles])
        else:
            mentions_text = "无"

        # 5. 渲染模板
        if os.path.exists('template.md'):
            try:
                with open('template.md', 'r', encoding='utf-8') as f:
                    tpl = f.read()
                md_text = (
                    tpl.replace('{{title}}', title)
                       .replace('{{datetime}}', now.strftime('%Y-%m-%d %H:%M:%S'))
                       .replace('{{content}}', final_content)
                       .replace('{{mentions}}', mentions_text)
                )
            except Exception as e:
                print(f"模板渲染出错: {e}, 使用默认格式")
                md_text = format_message(title, final_content)
        else:
            md_text = format_message(title, final_content)
        
        # 6. 发送
        send_markdown_msg(
            markdown_text=md_text,
            at_mobiles=at_mobiles,
            at_user_ids=task.get('at_user_ids', []),
            is_at_all=is_at_all
        )
        found_task = True
    
    if not found_task:
        print("本次运行未匹配到待发送任务。")

if __name__ == "__main__":
    run_scheduler()
