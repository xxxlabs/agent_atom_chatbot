import re
import json
import requests
from .llm import llm_haiku
from loguru import logger
from .utils import get_timestemp
from .prompt import system_prompt_general_chat, system_prompt_translation
from langchain_core.messages import SystemMessage, HumanMessage

def get_keyword(keyword):
    if len(keyword) < 1: return keyword
    system_message = SystemMessage(system_prompt_translation)
    human_message = HumanMessage(f"The user input is: {keyword}.")
    try:
        result = llm_haiku.invoke([human_message, system_message]).content
        pattern = "###(.*?)###"
        return re.findall(pattern, result)[0]
    except Exception as e:
        logger.error(e)
        return keyword

def log_and_post(url, headers, data_req):
    try:
        logger.info(f"API request: {data_req}")
        response = requests.post(url, headers=headers, data=json.dumps(data_req))
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"HTTP request failed: {e}")
        raise

def search(start_time: str, end_time: str, label_type_list: list, keyword: str, device_id: str, user_id: str, timezone="Asia/Tokyo") -> str:
    result = ""
    search_existed = False
    timestamp_start = get_timestemp(start_time, timezone)
    timestamp_end = get_timestemp(end_time, timezone)
    keyword = get_keyword(keyword)
    url = "http://internal-alb-agent-common-2147023048.us-west-2.elb.amazonaws.com/api/v1/chatbot/event/search"
    headers = {"Content-Type": "application/json"}
    data_req = {
        "deviceId": device_id,
        "userId": user_id,
        "startTime": timestamp_start,
        "endTime": timestamp_end,
        "labelTypeList": label_type_list,
        "keyWord": keyword
    }
    try:
        response = log_and_post(url, headers, data_req)
        data = response.json()
        event_list = data.get("data", {}).get("eventList", [])
        is_viewsay = data.get("data", {}).get("viewsay", False)
        logger.info(f"API result: {data}")
        if event_list:
            search_existed = True
            result = "I have found all the videos you are interested in through the video search tool and sent them to you. Please check them later."
        else:
            result = "I searched for the time period you're interested in and couldn't find any relevant videos."
    except Exception as e:
        result = "An error occurred while searching for related videos"
        logger.error(e)
    return "###Form1###\n"+result, search_existed, is_viewsay

def setting_camera_voc_switch(state: str) -> str:
    mapping = {"1": "on", "2": "off"}
    return f"###Form1###\nsetting the camera voc switch: {mapping.get(state, 'unknown')}"

def control_camera_reset(reset: str, device_id: str) -> str:
    if reset not in ["1", "0"]:
        return "###Form1###\nThe parameters for controlling the PTZ reset are incorrect. You need to chat with the user to call it again."
    active_type = int(reset)
    url = "http://internal-alb-agent-common-2147023048.us-west-2.elb.amazonaws.com/api/v1/chatbot/customParams/set"
    headers = {"Content-Type": "application/json"}
    data_req = {"deviceId": device_id, "activeType": active_type}
    try:
        response = log_and_post(url, headers, data_req)
        data = response.json()
        logger.info(f"API result: {data}")
        if data.get("code", "") == 1006:
            return "###Form1###\ndevice is offline"
        if data.get("code", "") == 0:
            return "###Form1###\nCamera reset operation has been performed."
    except Exception as e:
        logger.error(e)
        return "###Form1###\nAn error occurred while reset the camera"

def qa_helper_product(query: str, session_id: str) -> str:
    url = "http://internal-alb-agent-common-2147023048.us-west-2.elb.amazonaws.com/api/v1/chatbot/openai/answer"
    headers = {"Content-Type": "application/json"}
    data_req = {"sessionId": session_id, "question": query}
    try:
        response = log_and_post(url, headers, data_req)
        data = response.json()
        logger.info(f"API result: {data}")
        return data.get("data", "")
    except Exception as e:
        logger.error(e)
        return "###Form2###\nThere were some errors while searching for relevant answers. Please try again later."

def general_chat(query: str) -> str:
    system_message = SystemMessage(system_prompt_general_chat)
    human_message = HumanMessage(query)
    result = llm_haiku.invoke([human_message, system_message]).content
    return "###Form2###\n" + result

def control_camera_rotation(direction: str, num: str, device_id: str) -> str:
    return "The device rotation function is not supported yet"

def submit_feedback(query: str, user_id: str, device_id: str) -> str:
    return "Submit feedback function is not supported yet, please try another entrance"

def setting_camera_voc_adjust(state: str, num: str, device_id:str, user_id) -> str:
    return "Currently, the volume adjustment function is not supported, only the sound switch function is supported."