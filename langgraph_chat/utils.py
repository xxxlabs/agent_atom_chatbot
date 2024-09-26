import os
import yaml
from datetime import datetime, timezone
from loguru import logger
from langchain.agents import tool
import pytz

# 常量映射
INTENT_MAPPING = {
    "search": "search",
    "control_camera_reset": "ptzReset",
    "setting_camera_voc_switch": "vocSwitch",
    "control_camera_rotation": "ptzRotation",
    "setting_camera_voc_adjust": "vocAdjust",
    "qa_helper_product": "qaHelper",
    "general_chat": "other",
    "None": "None",
    "submit_feedback": "feedback"
}
PARAM_MAPPING = {
    "start_time": "startTime",
    "end_time": "endTime",
    "label_type_list": "labelTypeList"
}
STOP_TOOL = ["search", "ptzReset", "vocSwitch", "qaHelper"]

# 获取数据库和SQS配置
def get_config():
    config = {
        "db_url": os.environ.get('DB_URL', ''),
        "db_name": os.environ.get('DB_NAME', ''),
        "db_user": os.environ.get('DB_USER', ''),
        "db_password": os.environ.get('DB_PWD', ''),
        "output_queue_url": os.environ.get('QUEUE_URL', ''),
        "region_name": os.environ.get('REGION_NAME_ATOM', ''),
        "aws_access_key_atom": os.environ.get('ACCESS_KEY_ATOM', ''),
        "aws_secret_access_key_atom": os.environ.get('SECRET_ACCESS_KEY_ATOM', '')
    }
    return config
    
def get_timestemp(time, timezone):
  timezone_obj = pytz.timezone(timezone)
  date_time = timezone_obj.localize(datetime.strptime(time, "%Y-%m-%d %H:%M:%S"))
  timestamp= int(date_time.timestamp()) * 1000
  return timestamp

def get_format_time(timezone):
    timezone = pytz.timezone(timezone)
    current_time = datetime.now(timezone)
    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
    return formatted_time

def create_function(name, description, parameters):
    param_list = ', '.join([f"{key}: {value['type']}" for key, value in parameters.items()])
    docstring = f'"""\n    {description}\n    Args:\n'
    for param, info in parameters.items():
        docstring += f"        {param}: {info['description']}\n"
    docstring += '    """'
    function_body = f"""
def {name}({param_list}):
    {docstring}
    result = ''
    return result
"""
    compiled_code = compile(function_body, "<string>", "exec")
    local_namespace = {}
    exec(compiled_code, globals(), local_namespace)
    func = local_namespace[name]
    func = tool(func)

    return  func

def get_tools(config):
    function_list = []
    try:
        if isinstance(config, str) and config.endswith('.yaml'):
            with open(config, 'r') as file:
                config = yaml.safe_load(file)
        if isinstance(config, dict):
            for func_config in config.get('functions', []):
                name = func_config['name']
                description = func_config['description']
                arguments = func_config['parameters']
                func = create_function(name, description, arguments)
                function_list.append(func)
        else:
            logger.error("Invalid configuration file.")
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
    return function_list

def to_camel_case(snake_str):
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def get_every_id(request):
    #获取相关id
    result_format = {"code": 200, "message": "success"}
    device_info = {
        "request_id": request.get('requestId', ''),
        "uuid": request.get('uuid', ''),
        "user_id": request.get('userId', ''),
        "device_id": request.get('deviceId', ''),
        "session_id": request.get('sessionId', '')
    }
    device_info_camel = {to_camel_case(k): v for k, v in device_info.items()}
    result_format.update(device_info_camel)
    return device_info, result_format

def get_format_result(abot, intent_type, intent_args, result_llm, timezone):
    result = {
        "actionType": INTENT_MAPPING.get(intent_type, "None"),
        "msgOut": result_llm,
        "param": {}
    }
    for key, value in intent_args.items():
        if key in PARAM_MAPPING:
            if key in ["start_time", "end_time"]:
                value = get_timestemp(value, timezone)
            result["param"][PARAM_MAPPING[key]] = value
        else:
            result["param"][key] = value
    if intent_type == "search":
        result["actionType"] = "searchViewsay" if abot.is_viewsay else "searchEvent"
        result["param"]["existed"] = abot.search_existed
    return result

if __name__ == "__main__":
    tool_list = get_tools('langgraph_chat/test.yaml')
    print(tool_list)