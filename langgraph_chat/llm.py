import boto3
from langchain_aws import ChatBedrockConverse
from typing import Any

def create_bedrock_client() -> Any:
    """创建并返回一个 Bedrock 客户端。"""
    return boto3.client(
        service_name="bedrock-runtime",
        region_name="us-west-2"
    )

def get_llm(model_id: str) -> ChatBedrockConverse:
    """根据给定的模型 ID 返回一个 ChatBedrockConverse 实例。
    
    Args:
        model_id (str): 模型 ID。
    
    Returns:
        ChatBedrockConverse: ChatBedrockConverse 实例。
    """
    bedrock_runtime = create_bedrock_client()
    return ChatBedrockConverse(
        client=bedrock_runtime,
        model_id=model_id,
        max_tokens=1000,
        temperature=0,
    )

def get_llm_haiku() -> ChatBedrockConverse:
    """返回 Haiku 模型的 ChatBedrockConverse 实例。"""
    model_id = "anthropic.claude-3-haiku-20240307-v1:0"
    return get_llm(model_id)

def get_llm_sonnet() -> ChatBedrockConverse:
    """返回 Sonnet 模型的 ChatBedrockConverse 实例。"""
    model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    return get_llm(model_id)

llm_haiku = get_llm_haiku()
llm_sonnet = get_llm_sonnet()
