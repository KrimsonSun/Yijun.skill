import sqlite3
import json
import argparse
import os

def parse_db(db_path, output_path="wechat_finetune_dataset.jsonl"):
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Extract only private chats (exclude @chatroom) and only text messages (Type=1)
    # This directly honors the user's constraint: "只能读取私聊内容" (only read private chat content)
    query = """
    SELECT strTalker, IsSender, CreateTime, strContent 
    FROM Message 
    WHERE Type = 1 AND strTalker NOT LIKE '%@chatroom%'
    ORDER BY strTalker, CreateTime
    """
    
    try:
        cursor.execute(query)
        messages = cursor.fetchall()
    except sqlite3.DatabaseError as e:
        print(f"Database error: {e}. Are you sure this is a decrypted SQLite database?")
        conn.close()
        return

    conn.close()
    
    if not messages:
        print("No private text messages found.")
        return

    # Process messages to create context-response pairs
    # Group by strTalker (the friend you are chatting with)
    chats = {}
    for talker, is_sender, time, content in messages:
        if talker not in chats:
            chats[talker] = []
        chats[talker].append({"is_sender": is_sender, "time": time, "content": content})
        
    dataset = []
    
    for talker, msgs in chats.items():
        # Simple sliding window: look for friend message followed by user message
        for i in range(len(msgs) - 1):
            if msgs[i]['is_sender'] == 0 and msgs[i+1]['is_sender'] == 1:
                # Time gap less than 1 hour (3600 seconds) to be considered a direct response
                if msgs[i+1]['time'] - msgs[i]['time'] < 3600:
                    dataset.append({
                        "messages": [
                            {"role": "system", "content": "You are a personalized assistant mimicking the user's conversational style."},
                            {"role": "user", "content": msgs[i]['content']},
                            {"role": "assistant", "content": msgs[i+1]['content']}
                        ]
                    })
                    
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print(f"Success! Distilled dataset generated with {len(dataset)} conversation pairs.")
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distill WeChat private chat history into a fine-tuning dataset.")
    parser.add_argument("db_path", help="Path to the decrypted SQLite database")
    parser.add_argument("--output", default="wechat_finetune_dataset.jsonl", help="Output JSONL file path")
    
    args = parser.parse_args()
    parse_db(args.db_path, args.output)
