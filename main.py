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

WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
SECRET = os.environ.get('SECRET')

def derive_title(md_text):
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith('#'):
            return s.lstrip('#').strip()
    return '提醒通知'

def get_beijing_time():
    """获取北京时间"""
    # GitHub Actions 默认是 UTC 时间，需要 +8 小时
    return datetime.utcnow() + timedelta(hours=8)

def format_message(title, content):
    now = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
    template = """### 📌 任务提醒：{title}

---
**📅 发送时间：** {datetime}

**💬 提醒内容：**
> {content}

---
#### 📋 任务状态
* **执行节点：** Gitee Go Cloud
* **发送渠道：** 钉钉自动化助手
* **安全策略：** HMAC-SHA256
"""
    return template.format(title=title, datetime=now, content=content)

def run_crawler(task):
    """
    【扩展接口】爬虫/外部数据源逻辑
    后续可在此处调用 requests/BeautifulSoup 爬取网站信息
    """
    source = task.get('source_url', '未知来源')
    return f"正在从 {source} 获取数据... (功能开发中)\n\n这是一个动态生成的内容示例。"

def get_task_content(task):
    """
    根据任务配置获取最终发送的内容
    支持静态文本和动态获取（如爬虫）
    """
    # 默认为 'static' 静态文本
    content_type = task.get('content_type', 'static')
    
    if content_type == 'static':
        return task.get('content', '无内容')
    elif content_type == 'crawler':
        return run_crawler(task)
    # 未来可扩展其他类型，如 'file', 'api' 等
    elif content_type == 'file':
        # 示例：从文件读取
        file_path = task.get('file_path')
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return "错误：指定的文件不存在"
        
    return f"未知的任务类型: {content_type}"

def load_local_config():
    path = 'config_local.json'
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            return cfg.get('WEBHOOK_URL') or WEBHOOK_URL, cfg.get('SECRET') or SECRET
    return WEBHOOK_URL, SECRET

def get_signed_url():
    url, secret = load_local_config()
    if not secret:
        return url
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))
    if '?' in url:
        return f"{url}&timestamp={timestamp}&sign={sign}"
    return f"{url}?timestamp={timestamp}&sign={sign}"

def send_markdown_msg(markdown_text, at_mobiles=[], at_user_ids=[], is_at_all=False):
    url = get_signed_url()
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
    
    res = requests.post(url, json=data, headers=headers)
    print(f"发送状态: {res.text}")

def run_scheduler():
    # 获取当前北京时间
    now = get_beijing_time()
    today = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')
    print(f"当前系统日期(北京时间): {today} {current_time}")

    # 读取任务列表
    with open('tasks.json', 'r', encoding='utf-8') as f:
        text = f.read()
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        tasks = json.loads(text)

    found_task = False
    for task in tasks:
        # 1. 检查日期是否匹配
        if task['date'] != today:
            continue
            
        # 2. 检查时间是否匹配（如果任务中定义了 time 字段）
        # 格式必须为 "HH:MM"，例如 "16:30"
        task_time = task.get('time')
        if task_time:
            if task_time != current_time:
                print(f"日期匹配但时间不匹配: 设定的 {task_time} vs 当前 {current_time}")
                continue

        print(f"匹配到今日任务: {task['content']}")
        title = task.get('title', '日程提醒')
        
        # 准备 @ 对象文本
        at_mobiles = task.get('at_mobiles', [])
        is_at_all = task.get('is_at_all', False)
        if is_at_all:
            mentions_text = "@所有人"
        elif at_mobiles:
            mentions_text = ' '.join([f"@{m}" for m in at_mobiles])
        else:
            mentions_text = "无"

        if os.path.exists('template.md'):
            tpl = open('template.md', 'r', encoding='utf-8').read()
            md_text = (
                tpl.replace('{{title}}', title)
                   .replace('{{datetime}}', now.strftime('%Y-%m-%d %H:%M:%S'))
                   .replace('{{content}}', final_content)
                   .replace('{{mentions}}', mentions_text)
            )
        else:
            md_text = format_message(title, final_content)
        
        send_markdown_msg(
            markdown_text=md_text,
            at_mobiles=at_mobiles,
            at_user_ids=task.get('at_user_ids', []),
            is_at_all=is_at_all
        )
        found_task = True
    
    if not found_task:
        print("当前时间无定时发送任务。")

if __name__ == "__main__":
    run_scheduler()
