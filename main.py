import argparse
import json
import logging
import os
import sys
import requests


# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler('tmp/bailing.log', encoding='utf-8')  # 文件输出
    ]
)

# Windows GBK 控制台日志编码错误修复
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# Chroma telemetry 错误日志压制
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
logging.getLogger('chromadb.telemetry.product.posthog').setLevel(logging.CRITICAL)
from bailing import robot
# 获取根 logger
logger = logging.getLogger(__name__)


def push2web(payload):
    try:
        data = json.dumps(payload, ensure_ascii=False)
        url = "http://127.0.0.1:5000/add_message"
        headers = {
          'Content-Type': 'application/json; charset=utf-8'
        }
        response = requests.request("POST", url, headers=headers, data=data.encode('utf-8'))
        logger.info(response.text)
    except Exception as e:
        logger.error(f"callback error：{payload}{e}")

def main():
    # Create the parser
    parser = argparse.ArgumentParser(description="Description of your script.")

    # Add arguments
    parser.add_argument('config_path', type=str, help="配置文件", default=None)
    # Parse arguments
    args = parser.parse_args()
    config_path = args.config_path
    bailing_robot = robot.Robot(config_path)
    bailing_robot.listen_dialogue(push2web)
    bailing_robot.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Description of your script.")

    # Add arguments
    parser.add_argument('--config_path', type=str, help="配置文件", default="config/config.yaml")

    # Parse arguments
    args = parser.parse_args()
    config_path = args.config_path

    # 创建 Robot 实例并运行
    robot = robot.Robot(config_path)
    robot.listen_dialogue(push2web)
    robot.run()
    
    # 确保程序退出
    logging.shutdown()
    os._exit(0)
