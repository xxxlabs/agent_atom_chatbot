import re
import time
import operator
from loguru import logger
from typing import Annotated, TypedDict
from datetime import datetime

from langchain_core.tools import StructuredTool
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langgraph.graph import END, StateGraph
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    ToolMessage,
    SystemMessage,
    AIMessage
)
from .prompt import system_prompt_detection, system_prompt_callback_chat, system_prompt_determine_language, system_prompt_search

from .llm import llm_haiku, llm_sonnet
from . tool_action import *
from .utils import get_format_time


def get_language(input_text):
    user_prompt_lang = HumanMessage(f"The user input is: {input_text}")
    system_prompt_lang = SystemMessage(system_prompt_determine_language)
    language = "Japanese"
    try:
        language_det = llm_haiku.invoke([user_prompt_lang, system_prompt_lang]).content
        pattern = "###(.*?)###"
        matches = re.findall(pattern, language_det)
        if matches:
            language = matches[0]
            language = "English" if language == "English" else "Japanese"
        else:
            logger.warning("No language detected in the response.")
    except Exception as e:
        logger.error(e)
    return language 

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    chat_history: ConversationBufferWindowMemory

class Agent:
    def __init__(self, tools: list[StructuredTool], checkpointer, setting_id):
        self.tools = {t.name: t for t in tools}
        self.graph = self._initialize_graph(checkpointer)
        self.chat_llm_haiku = llm_haiku
        self.chat_llm_sonnet = llm_haiku
        self.model_haiku = self.chat_llm_haiku.bind_tools(tools)
        self.model_sonnet = self.chat_llm_sonnet.bind_tools(tools)
        self.thread = {"configurable": {"thread_id": "main"}}
        self.setting_id = setting_id
        self.device_id = setting_id.get("device_id")
        self.user_id = setting_id.get("user_id")
        self.session_id = setting_id.get("session_id")
        self.search_existed = False
        self.is_viewsay = False
        self.intent_type = ""
        self.language = "Japanese"
        self.timezone = "Asia/Tokyo"

    def _initialize_graph(self, checkpointer):
        graph = StateGraph(AgentState)
        graph.add_node("detection", self.intent_detection)
        graph.add_node("decision", self.intention_decision)
        graph.add_node("tool_action", self.take_tool_action)
        graph.add_node("summary_llm", self.call_bedrock)
        graph.add_conditional_edges("detection", self.analyze, {True: "decision", False: "tool_action", "None": "summary_llm"})
        graph.add_conditional_edges("decision", self.exists_action, {True: "tool_action", False: END})
        graph.add_edge("tool_action", "summary_llm")
        # graph.add_edge("tool_action", END)
        graph.set_entry_point("detection")
        return graph.compile(checkpointer=checkpointer)
    
    def intent_detection(self, state: AgentState):
        try:
            t1 = time.time()
            messages = state["messages"]
            system_prompt = SystemMessage(system_prompt_detection)
            messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
            messages.append(system_prompt)
            message = self.model_sonnet.invoke(messages)
            logger.info("Intent detection success")
            logger.info(f"Intent detection time: {time.time()-t1}")
            return {"messages": [message]}
        except Exception as e:
            logger.error(f"Intent detection error: {e}")
            return {"messages": []}
        
    def analyze(self, state: AgentState):
        try:
            self.intent_type = ""
            tool_calls = state["messages"][-1].tool_calls
            flag = False
            logger.info(f"intent detection count: {len(tool_calls)}")
            if len(tool_calls) == 0: flag = "None"
            for t in tool_calls:
                name = t["name"]
                flag = True if name in ["search"] else False
                logger.info(f"intent detection type: {name}")
                self.intent_type = name
            return flag
        except Exception as e:
            logger.error(f"Analyze error: {e}")
            return False

    def intention_decision(self, state: AgentState):
        try:
            t1 = time.time()
            system_prompt = SystemMessage(system_prompt_search)
            messages = state["messages"]
            if isinstance(messages[-1], AIMessage):
                del messages[-1]
            messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
            messages.append(system_prompt)
            message = self.model_sonnet.invoke(messages)
            logger.info("Intent decision success")
            logger.info(f"Intent decision time: {time.time()-t1}")
            return {"messages": [message]}
        except Exception as e:
            logger.error(f"Intention decision error: {e}")
            return {"messages": []}
    
    def exists_action(self, state: AgentState):
        try:
            result = state["messages"][-1]
            return len(result.tool_calls) > 0
        except Exception as e:
            logger.error(f"Exists action error: {e}")
            return False
        
    def _invoke_tool(self, tool_call):
        try:
            action_map = {
                "search": lambda **args: search(**args, device_id=self.device_id, user_id=self.user_id, timezone=self.timezone),
                "control_camera_reset": lambda **args: control_camera_reset(**args, device_id=self.device_id),
                "control_camera_rotation": lambda **args: control_camera_rotation(**args, device_id=self.device_id),
                "setting_camera_voc_switch": lambda **args: setting_camera_voc_switch(**args),
                "setting_camera_voc_adjust": lambda **args: setting_camera_voc_adjust(**args, device_id=self.device_id, user_id=self.user_id),
                "qa_helper_product": lambda **args: qa_helper_product(**args, session_id=self.session_id),
                "submit_feedback": lambda **args: submit_feedback(**args, device_id=self.device_id, user_id=self.user_id)
            }
            action_name = tool_call["name"]
            if action_name in action_map:
                if action_name == "search":
                    result, self.search_existed, self.is_viewsay = action_map[action_name](**tool_call["args"])
                else:
                    result = action_map[action_name](**tool_call["args"])
            else:
                result = general_chat(**tool_call["args"])
            return result
        except Exception as e:
            logger.error(f"Error invoking tool {tool_call['name']}: {e}")
            return str(e)
        
    def take_tool_action(self, state: AgentState):
        try:
            tool_calls = state["messages"][-1].tool_calls
            results = []
            for t in tool_calls:
                logger.info(f"Calling: {t}")
                if t["name"] not in self.tools:
                    logger.warning("Bad tool name, retrying")
                    result = "bad tool name, retry"
                else:
                    t1 = time.time()
                    result = self._invoke_tool(t)
                    logger.info(f"Tool call time: {time.time()-t1}")
                logger.info(f"The result of invoke tool: {result}")
                results.append(ToolMessage(tool_call_id=t["id"], name=t["name"], content=str(result)))
            logger.info("Invoke tool success, back to the model!")
            return {"messages": results}
        except Exception as e:
            logger.error(f"Take tool action error: {e}")
            return {"messages": []}

    def call_bedrock(self, state: AgentState):
        def create_user_prompt(messages, language):
            if isinstance(messages[-1], ToolMessage) and isinstance(messages[-2], AIMessage) and isinstance(messages[-3], HumanMessage):
                return messages[-3].content + "\nThe results of intention execution component is: " + messages[-1].content + f"\n{language}" + "\n###For the results of Table 1, you only need to answer in one sentence. For Table 2, your response needs to be concise and clear, covering the information of the tool and conveying it to the user in as few words as possible.###"
            elif isinstance(messages[-1], AIMessage) and isinstance(messages[-2], HumanMessage):
                return messages[-2].content + "\n###The results of intention execution component is: No tool was found to help the user accomplish his intent.###" + f"\n{language}" + "\n###You need to respond to the user with one or two sentences based on the user's input and historical context.###"
            return ""

        t1 = time.time()
        language = f"####Your reply should be in {self.language}###" if self.language else "Japanese"
        system_prompt = SystemMessage(system_prompt_callback_chat)
        messages = state["messages"]
        messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
        # 智能问答直接回复
        if isinstance(messages[-1], ToolMessage) and messages[-1].name in ["qa_helper_product"]:
            text = messages[-1].content
            if "###Form2###" not in text:
                return {"messages": [AIMessage(text)]}
        #非智能问答过模型
        user_prompt = create_user_prompt(messages, language)
        if user_prompt:
            messages = messages[:-3] + [HumanMessage(user_prompt)] if isinstance(messages[-1], ToolMessage) else messages[:-2] + [HumanMessage(user_prompt)]
        
        messages.append(system_prompt)
        message = self.chat_llm_haiku.invoke(messages)
        
        if not message.content and isinstance(messages[-2], ToolMessage) and messages[-2].name in ["qa_helper_product", "general_chat"]:
            message = AIMessage(messages[-2].content)
        
        logger.info(f"Call bedrock time: {time.time()-t1}")
        return {"messages": [message]}

    def show_graph(self):
        f = open("graph.png", "wb")
        f.write(self.graph.get_graph().draw_mermaid_png())
        f.close()

    def process(self, input_text, history, timezone):
        self.search_existed = False
        self.is_viewsay = False
        self.timezone = timezone
        history_messages = [
            HumanMessage(his["content"]) if his["role"] == "user" else AIMessage(his["content"])
            for his in history
        ]
        t1 = time.time()
        self.language = get_language(input_text)
        logger.info(f"Language detected time: {time.time()-t1}")
        time_now = get_format_time(timezone)
        input_prompt = f"***Current system time: {time_now}***\nThe user input is: {input_text}."
        input_prompt_log = input_prompt.replace("\n", "")
        logger.info(f"Input graph: {input_prompt_log}")
        history_messages.append(HumanMessage(input_prompt))
        thread = {"configurable": {"thread_id": "main"}}
        t2 = time.time()
        result = self.graph.invoke({"messages": history_messages}, thread)
        logger.info(f"Graph invoke time: {time.time()-t2}")
        
        return result