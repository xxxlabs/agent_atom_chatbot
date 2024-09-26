import os
import json
import time
import boto3
from loguru import logger
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AIMessage, ToolMessage
from langgraph_chat.db import ChatDB
from langgraph_chat.chat_agent import Agent
from langgraph_chat.utils import INTENT_MAPPING, PARAM_MAPPING, get_timestemp, get_config, get_tools, get_every_id, get_format_result

config = get_config()
db_server = ChatDB(config)
tools = get_tools('langgraph_chat/tool_manager.yaml')

sqs = boto3.client(
    "sqs",
    aws_access_key_id=config["aws_access_key_atom"],
    aws_secret_access_key=config["aws_secret_access_key_atom"],
    region_name=config["region_name"]
)

def process_input_text(input_text, every_id, history, timezone):
    memory = SqliteSaver.from_conn_string(":memory:")
    abot = Agent(tools, memory, every_id)
    result = abot.process(input_text, history, timezone)["messages"]
    result_content = result[-1].content
    result_llm = ""
    if result_content == [] and isinstance(result[-2], ToolMessage):
        result_llm = result[-2].content
    elif isinstance(result_content, list) and len(result_content) > 1:
        for _r in result_content:
            if "text" in _r.keys():
                result_llm = _r["text"]
    else:
        result_llm = result_content

    intent_type, intent_args = "None", {}
    if isinstance(result[-2], ToolMessage) and isinstance(result[-3], AIMessage):
        tool_call = result[-3].tool_calls[0]
        intent_type = tool_call["name"]
        intent_args = tool_call["args"]

    return get_format_result(abot, intent_type, intent_args, result_llm, timezone), result_llm
    
def lambda_handler(event, context):
    try:
        print(f"Records: {event['Records']}")
        print(f"#############new request##############")
        t1 = time.time()
        body_str = event['Records'][0]['body']
        request = json.loads(body_str)
        logger.info(f"request: {request}")
        input_text = request.get('msgIn', None)
        timezone = request.get('timezone', "Asia/Tokyo").replace("\\", "")
        every_id, result_format = get_every_id(request)
        history = db_server.get_history_session(every_id)
        if input_text:
                res, result_llm = process_input_text(input_text, every_id, history, timezone)
                result_format.update(res)
                logger.info(f"llm out: {result_llm}")
                _ = db_server.update_db(every_id, data={"tool_type": res["actionType"], "msg_user": input_text, "msg_assistant": result_llm})
        else:
            result_format = {"code": 500, "message": "input is null"}

        logger.info(f"return :{result_format}")
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        result_format = {"code": 600, "message": "Internal server error"}
    logger.info(f"Chatbot time cost: {time.time() - t1}")
    res = sqs.send_message(QueueUrl=config["output_queue_url"], MessageBody=json.dumps(result_format))
    logger.info(f"callback sqs mse:{res}")
    logger.info(f"Toatl time cost: {time.time() - t1}")
    return result_format