import os
import time
import psycopg2
from datetime import datetime
from loguru import logger

class Database:
    def __init__(self, host, database, user, password, port=5432):
        self.connection_details = {
            "host": host,
            "dbname": database,
            "user": user,
            "password": password,
            "port": port
        }

    def _create_connection(self):
        try:
            con = psycopg2.connect(**self.connection_details)
            return con
        except Exception as e:
            logger.info("连接DB失败")
            logger.info(f"The error '{e}' occurred")
            return None

    def execute_sql(self, query, params=None):
        conn = None
        try:
            conn = self._create_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                conn.commit()
        except Exception as e:
            logger.info(f"The error '{e}' occurred")
        finally:
            if conn is not None:
                conn.close()

    def execute_read_query(self, query, params=None):
        conn = None
        try:
            conn = self._create_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"The error '{e}' occurred")
            return []
        finally:
            if conn is not None:
                conn.close()

    # 插入或更新数据
    def insert_or_update(self, request_id, uuid, user_id, device_id, session_id, msg_user, msg_assistant, tool_type, time):
        try:
            msg_user = msg_user.replace("'", "''")
            msg_assistant = msg_assistant.replace("'", "''")
            upsert_query = f"""INSERT INTO chat_history_table (request_id, uuid, user_id, device_id, session_id, msg_user, msg_assistant, tool_type, time) VALUES ('{request_id}', '{uuid}', '{user_id}', '{device_id}', '{session_id}', '{msg_user}', '{msg_assistant}', '{tool_type}', {time})"""
            self.execute_sql(upsert_query)
            logger.info(f"Data inserted successfully: {str(upsert_query)}.")
        except Exception as e:
            logger.error(e)

    # 查询数据
    def select_data(self, request_id, uuid, user_id, device_id, session_id):
        select_query = f"""
           WITH SortedMessages AS (
                SELECT *
                FROM chat_history_table
                WHERE user_id = '{user_id}' AND device_id = '{device_id}'
                ORDER BY time DESC
            ),
            FirstNonNone AS (
                SELECT MAX(time) AS first_non_none_time
                FROM SortedMessages
                WHERE tool_type <> 'None' AND tool_type <> 'other'
            )
            SELECT *
            FROM SortedMessages
            WHERE time > (SELECT first_non_none_time FROM FirstNonNone)
            ORDER BY time DESC;
            """
        select_query_2 = f"""
            WITH SortedMessages AS (
                SELECT *
                FROM chat_history_table
                WHERE user_id = '{user_id}' AND device_id = '{device_id}'
                ORDER BY time DESC
            ),
            NonNoneMessages AS (
                SELECT time
                FROM SortedMessages
                WHERE tool_type <> 'None' AND tool_type <> 'other'
                ORDER BY time DESC
                LIMIT 1 OFFSET 1 -- 获取第二大的时间
            )
            SELECT *
            FROM SortedMessages
            WHERE time > (SELECT time FROM NonNoneMessages)
            ORDER BY time DESC;
            """
        select_query_3 = f"""
        
            SELECT *
            FROM chat_history_table
            WHERE user_id = '{user_id}' AND device_id = '{device_id}' AND session_id = '{session_id}'
            ORDER BY time DESC
            LIMIT 3;"""
        
        return self.execute_read_query(select_query_3)

    # 查询所有数据
    def select_all_data(self):
        select_query = "SELECT * FROM chat_history_table ORDER BY time DESC;"
        return self.execute_read_query(select_query)


class ChatDB:
    def __init__(self, config):
        self.db_server = Database(config["db_url"], config["db_name"], config["db_user"], config["db_password"])

    def get_history_session(self, every_id):
        try:
            res = self.db_server.select_data(**every_id)
            history = []
            for r in res[::-1]:
                history.append({"role":"user", "content":r[5]})
                history.append({"role":"assistant", "content":r[6]})
            logger.info(f"get history db: {history}")
            return history
        except Exception as e:
            logger.error(f"Error getting history session: {e}")
            return []

    def update_db(self, every_id, data={}):
        try:
            data["time"] = int(time.time())*1000
            insert_template = {**every_id, **data}
            self.db_server.insert_or_update(**insert_template)
            return "success"
        except Exception as e:
            logger.error(f"Error updating DB: {e}")
            return "failure"