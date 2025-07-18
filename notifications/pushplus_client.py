import requests
import logging

logger = logging.getLogger(__name__)


class PushPlusClient:
    def __init__(self, token):
        self.token = token
        self.url = "https://www.pushplus.plus/send"

    def send_notification(self, title, content, template="markdown"):
        if not self.token:
            logger.warning(
                "PushPlus token is not configured. Notification will not be sent."
            )
            return

        payload = {
            "token": self.token,
            "title": title,
            "content": content,
            "template": template,
        }
        try:
            response = requests.post(self.url, json=payload)
            response.raise_for_status()  # Raise an exception for bad status codes
            result = response.json()
            if result.get("code") == 200:
                logger.info("PushPlus notification sent successfully.")
            else:
                logger.error(
                    f"Failed to send PushPlus notification: {result.get('msg')}"
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"An error occurred while sending PushPlus notification: {e}")
