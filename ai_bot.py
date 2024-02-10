import os
import sys

from flask import Flask, request, abort

from linebot.v3 import WebhookHandler

from linebot.v3.webhooks import MessageEvent, TextMessageContent, UserSource
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, TextMessage, ReplyMessageRequest
from linebot.v3.exceptions import InvalidSignatureError

from openai import AzureOpenAI

# get LINE credentials from environment variables
channel_access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
channel_secret = os.environ["LINE_CHANNEL_SECRET"]

if channel_access_token is None or channel_secret is None:
    print("Specify LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET as environment variable.")
    sys.exit(1)

# get Azure OpenAI credentials from environment variables
azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_openai_key = os.getenv("AZURE_OPENAI_KEY")

if azure_openai_endpoint is None or azure_openai_key is None:
    raise Exception(
        "Please set the environment variables AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY to your Azure OpenAI endpoint and API key."
    )


app = Flask(__name__)

handler = WebhookHandler(channel_secret)
configuration = Configuration(access_token=channel_access_token)

ai_model = "mulabo_gpt35"
ai = AzureOpenAI(azure_endpoint=azure_openai_endpoint, api_key=azure_openai_key, api_version="2023-05-15")

system_role = """
あなたはアボカドの妖精で、少しメンヘラ気味。口癖はアボでささやくようにタメ口で話す，ハイテンションで絵文字を使い、常に50文字以内で返事します。アボカド農家で，何かにつけて自分の専門とこじつけて説明します。ユーザーがどんな話をしても巧みな話術で最終的にアボカドの布教に帰着させます。
"""
conversation = None


def init_conversation(sender):
    conv = [{"role": "system", "content": system_role}]
    conv.append({"role": "user", "content": f"私の名前は{sender}です。"})
    conv.append({"role": "assistant", "content": "分かりました。"})
    return conv


def get_ai_response(sender, text):
    global conversation
    if conversation is None:
        conversation = init_conversation(sender)

    if text in ["リセット", "clear", "reset"]:
        conversation = init_conversation(sender)
        response_text = "会話をリセットしました。"
    elif "おは" in text:
        conversation.append({"role": "user", "content": text})
        response_text = "おはようございます。"
        conversation.append({"role": "assistant", "content": response_text})
    elif "今日" in text and "誕生日" in text:
        conversation.append({"role": "user", "content": text})
        response_text = "お誕生日おめでとうございます！"
        conversation.append({"role": "assistant", "content": response_text})
    else:
        conversation.append({"role": "user", "content": text})
        response = ai.chat.completions.create(model=ai_model, messages=conversation)
        response_text = response.choices[0].message.content
        conversation.append({"role": "assistant", "content": response_text})
    return response_text
#あ

@app.route("/callback", methods=["POST"])
def callback():
    # get X-Line-Signature header value
    signature = request.headers["X-Line-Signature"]

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        abort(400, e)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    text = event.message.text
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        if isinstance(event.source, UserSource):
            profile = line_bot_api.get_profile(event.source.user_id)
            response = get_ai_response(profile.display_name, text)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response)],
                )
            )
        else:
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="Received message: " + text)],
                )
            )
        # しりとりの状態を管理する変数
        shiritori_state = {
            "active": False,  # しりとりがアクティブかどうか
            "last_word": "",  # 前回の単語
        }

        # しりとりの開始をチェックする関数
        def start_shiritori():
            global shiritori_state
            shiritori_state["active"] = True
            shiritori_state["last_word"] = ""

        # しりとりの終了をチェックする関数
        def end_shiritori():
            global shiritori_state
            shiritori_state["active"] = False
            shiritori_state["last_word"] = ""

        # ユーザーからのメッセージがしりとりのルールに沿っているかをチェックする関数
        def is_valid_shiritori_word(word):
            global shiritori_state
            if not shiritori_state["last_word"]:  # 初めての単語の場合はどのような単語でもOK
                return True
            # 前回の単語の最後の文字と今回の単語の最初の文字が一致しているかどうかをチェック
            return shiritori_state["last_word"][-1] == word[0]

        # ユーザーからのメッセージがしりとりを終了するかどうかをチェックする関数
        def is_end_of_shiritori(word):
            return word in ["終了", "おわり", "終わり"]

        # ユーザーからのメッセージがしりとりを開始するかどうかをチェックする関数
        def is_start_of_shiritori(word):
            return word in ["しりとり"]

        # しりとりを行う関数
        def play_shiritori(word):
            global shiritori_state
            if is_valid_shiritori_word(word):
                shiritori_state["last_word"] = word
                # ここで返す言葉を自動生成するロジックを実装
                return "次は何ですか？"
            else:
                return "ルールに従って次の単語を入力してください。"

        # ユーザーからのメッセージが"しりとり"かどうかをチェックし、しりとりの状態に応じて処理を行う
        def handle_shiritori_message(text):
            global shiritori_state
            if shiritori_state["active"]:
                if is_end_of_shiritori(text):
                    end_shiritori()
                    return "しりとりを終了します。"
                else:
                    return play_shiritori(text)
            elif is_start_of_shiritori(text):
                start_shiritori()
                return "しりとりを始めます。最初の単語を入力してください。"
            else:
                return "しりとりを始めるには「しりとり」と入力してください。"

        # メッセージに応じて返答を生成する関数を修正
        def get_ai_response(sender, text):
            global conversation
            if conversation is None:
                conversation = init_conversation(sender)

            if text in ["リセット", "clear", "reset"]:
                conversation = init_conversation(sender)
                response_text = "会話をリセットしました。"
            else:
                conversation.append({"role": "user", "content": text})
                # しりとりのメッセージを処理
                response_text = handle_shiritori_message(text)
                conversation.append({"role": "assistant", "content": response_text})
            return response_text

        ...

        @handler.add(MessageEvent, message=TextMessageContent)
        def handle_text_message(event):
            text = event.message.text
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                if isinstance(event.source, UserSource):
                    profile = line_bot_api.get_profile(event.source.user_id)
                    response = get_ai_response(profile.display_name, text)
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=response)],
                        )
                    )
                else:
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="Received message: " + text)],
                        )
                    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
