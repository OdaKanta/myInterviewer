/mnt/myInterviewer/interview_session/views.py
def first_question(self, request, pk=None)
で最初の問題生成

def explanation_summary(self, request, pk=None):
文字の始めだけ表示してるだけ．別に要らない
HTML側で表示しているけども必要ないので機能削除対象


AnswerViewSetのcreateで問題生成
実態は_generate_next_question
現状は質問と回答と最初の質問文を基に問題を生成
トピック判定とそれに基づくトピック変更の機能は入っていない


Audioファイルが保存されていない（要検討）
