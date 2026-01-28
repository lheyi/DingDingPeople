import os
import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import json
import re
from datetime import datetime

# 从环境变量读取（请在 Gitee 变量管理中配置）
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
SECRET = os.environ.get('SECRET')

def get_signed_url():
    timestamp = str(round(time.time() * 1000))
    secret_enc = SECRET.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, SECRET)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote(base64.b64encode(hmac_code))
    return f"{WEBHOOK_URL}&timestamp={timestamp}&sign={sign}"

def send_dingtalk_msg(content, at_mobiles=[], is_at_all=False):
    url = get_signed_url()
    headers = {"Content-Type": "application/json"}
    
    data = {
        "msgtype": "text",
        "text": {
            "content": content
        },
        "at": {
            "atMobiles": at_mobiles,
            "isAtAll": is_at_all
        }
    }
    
    res = requests.post(url, data=json.dumps(data), headers=headers)
    print(f"发送状态: {res.text}")

def run_scheduler():
    # 获取今天日期，格式为 YYYY-MM-DD
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"当前系统日期: {today}")

    # 读取任务列表
    with open('tasks.json', 'r', encoding='utf-8') as f:
        text = f.read()
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        tasks = json.loads(text)

    found_task = False
    for task in tasks:
        if task['date'] == today:
            print(f"匹配到今日任务: {task['content']}")
            send_dingtalk_msg(
                content=task['content'],
                at_mobiles=task.get('at_mobiles', []),
                is_at_all=task.get('is_at_all', False)
            )
            found_task = True
    
    if not found_task:
        print("今日无定时发送任务。")

if __name__ == "__main__":
    run_scheduler()
