import json
from openai import OpenAI
from django.conf import settings
from knowledge_tree.models import KnowledgeNode, DocumentChunk
from interview_session.models import Question, Answer, InterviewSession


class SocraticQuestionGenerator:
    """ソクラテス式質問生成器"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
    def generate_question(self, node, session, depth_level=1, previous_answers=None):
        """指定されたノードに対してソクラテス式質問を生成"""
        try:
            # コンテキストを構築
            context = self._build_context(node, session, previous_answers)
            
            # 質問タイプを決定
            question_type = self._determine_question_type(depth_level, previous_answers)
            
            # LLMプロンプトを構築
            prompt = self._build_prompt(node, context, question_type, depth_level)
            
            # LLMで質問を生成
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            question_content = response.choices[0].message.content.strip()
            
            # 質問をデータベースに保存
            question = Question.objects.create(
                session=session,
                node=node,
                content=question_content,
                question_type=question_type,
                depth_level=depth_level,
                context_chunks=context.get('chunks', [])
            )
            
            return question
            
        except Exception as e:
            print(f"Question generation error: {e}")
            return None
    
    def _build_context(self, node, session, previous_answers):
        """質問生成のためのコンテキストを構築"""
        context = {
            'node_info': {
                'title': node.title,
                'description': node.description,
                'understanding_score': node.understanding_score
            },
            'chunks': [],
            'previous_answers': []
        }
        
        # 関連チャンクを取得
        chunks = node.chunks.all()[:3]  # 最大3チャンク
        context['chunks'] = [
            {
                'content': chunk.content,
                'page_number': chunk.page_number
            }
            for chunk in chunks
        ]
        
        # 過去の回答を取得
        if previous_answers:
            context['previous_answers'] = [
                {
                    'question': answer.question.content,
                    'answer': answer.content,
                    'score': answer.understanding_score
                }
                for answer in previous_answers
            ]
        
        return context
    
    def _determine_question_type(self, depth_level, previous_answers):
        """深掘りレベルと過去の回答に基づいて質問タイプを決定"""
        if depth_level == 1:
            return 'clarification'  # 明確化
        elif depth_level == 2:
            return 'elaboration'    # 詳細化
        elif depth_level == 3:
            return 'application'    # 応用
        else:
            return 'evaluation'     # 評価
    
    def _build_prompt(self, node, context, question_type, depth_level):
        """LLMプロンプトを構築"""
        base_prompt = f"""
        最初に必ず夜の挨拶をしてください。重要です。夜の挨拶を必ずしてください。
        以下の情報に基づいて、学習者に対するソクラテス式の質問を1つ生成してください。

        トピック: {context['node_info']['title']}
        説明: {context['node_info']['description']}
        現在の理解度: {context['node_info']['understanding_score']:.2f}

        参考資料:
        """
        
        # チャンク情報を追加
        for chunk in context['chunks']:
            base_prompt += f"\n- ページ{chunk['page_number']}: {chunk['content'][:200]}..."
        
        # 過去の回答情報を追加
        if context['previous_answers']:
            base_prompt += "\n\n過去の質問と回答:"
            for qa in context['previous_answers']:
                base_prompt += f"\nQ: {qa['question']}\nA: {qa['answer'][:100]}..."
        
        # 質問タイプ別の指示を追加
        type_instructions = {
            'clarification': '学習者の理解を明確にする質問を作成してください。',
            'elaboration': '学習者により詳細な説明を求める質問を作成してください。',
            'application': '学習した内容を実際の場面で応用する質問を作成してください。',
            'connection': '他の概念との関連性を探る質問を作成してください。',
            'evaluation': '学習者に批判的思考を促す評価的な質問を作成してください。'
        }
        
        base_prompt += f"\n\n{type_instructions.get(question_type, '')}"
        base_prompt += f"\n\n質問は日本語で、学習者が考えやすいように具体的で明確にしてください。"
        
        return base_prompt
    
    def _get_system_prompt(self):
        """システムプロンプトを取得"""
        return """
        あなたは経験豊富な教育者で、ソクラテス式問答法の専門家です。
        学習者の理解を深めるための効果的な質問を生成することが得意です。
        
        質問の特徴:
        - 学習者に考えさせる open-ended な質問
        - 段階的に理解を深める質問
        - 具体例や実際の応用を促す質問
        - 学習者の既存知識と新しい概念を結び付ける質問
        
        質問は1つだけ生成し、質問文のみを返してください。
        ただし、最初に必ず夜の挨拶をしてください。重要です。夜の挨拶を必ずしてください。
        """


class AnswerEvaluator:
    """回答評価器"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def evaluate_answer(self, answer):
        """回答を評価して理解度スコアと次のアクションを決定"""
        try:
            question = answer.question
            node = question.node
            
            # 評価プロンプトを構築
            prompt = self._build_evaluation_prompt(question, answer, node)
            
            # LLMで評価
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self._get_evaluation_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            # 評価結果を解析
            evaluation_text = response.choices[0].message.content
            evaluation = self._parse_evaluation(evaluation_text)
            
            # 回答を更新
            answer.understanding_score = evaluation['score']
            answer.needs_deeper_questioning = evaluation['needs_deeper_questioning']
            answer.save()
            
            # ノードの理解度を更新
            self._update_node_understanding(node, answer)
            
            return evaluation
            
        except Exception as e:
            print(f"Answer evaluation error: {e}")
            return {
                'score': 0.5,
                'needs_deeper_questioning': True,
                'feedback': '評価中にエラーが発生しました。'
            }
    
    def _build_evaluation_prompt(self, question, answer, node):
        """評価プロンプトを構築"""
        return f"""
        以下の質問に対する学習者の回答を評価してください。

        トピック: {node.title}
        トピック説明: {node.description}
        
        質問: {question.content}
        質問タイプ: {question.get_question_type_display()}
        深掘りレベル: {question.depth_level}
        
        学習者の回答: {answer.content}
        
        以下の形式でJSONとして評価結果を返してください:
        {{
            "score": 0.8,
            "needs_deeper_questioning": false,
            "feedback": "回答の評価コメント",
            "strengths": ["良い点1", "良い点2"],
            "improvements": ["改善点1", "改善点2"]
        }}
        
        scoreは0.0から1.0の間で、理解度を表します。
        needs_deeper_questioningは、さらに深掘り質問が必要かどうかを示します。
        """
    
    def _get_evaluation_system_prompt(self):
        """評価用システムプロンプト"""
        return """
        あなたは学習評価の専門家です。学習者の回答を公正かつ建設的に評価してください。
        
        評価基準:
        - 内容の正確性
        - 理解の深さ
        - 具体例の使用
        - 論理的な構成
        - 概念間の関連性の理解
        
        スコア基準:
        - 0.9-1.0: 優秀な理解、具体例や応用まで言及
        - 0.7-0.8: 良い理解、基本概念を正しく説明
        - 0.5-0.6: 基本的理解、一部不正確または不完全
        - 0.3-0.4: 限定的理解、重要な部分が欠けている
        - 0.0-0.2: 理解不足、大幅な誤解がある
        """
    
    def _parse_evaluation(self, evaluation_text):
        """評価結果を解析"""
        try:
            return json.loads(evaluation_text)
        except json.JSONDecodeError:
            # フォールバック評価
            return {
                'score': 0.5,
                'needs_deeper_questioning': True,
                'feedback': '評価結果の解析に失敗しました。',
                'strengths': [],
                'improvements': []
            }
    
    def _update_node_understanding(self, node, answer):
        """ノードの理解度を更新"""
        # 同じノードの過去の回答も考慮して平均を計算
        node_answers = Answer.objects.filter(question__node=node)
        if node_answers.exists():
            avg_score = sum(a.understanding_score for a in node_answers) / len(node_answers)
            node.understanding_score = avg_score
            node.save()


class QuestionSequenceManager:
    """質問シーケンス管理器"""
    
    def __init__(self):
        self.generator = SocraticQuestionGenerator()
        self.evaluator = AnswerEvaluator()
    
    def get_next_question(self, session):
        """次の質問を取得"""
        current_node = session.current_node
        
        if not current_node:
            return None
        
        # 現在のノードに対する過去の質問と回答を取得
        previous_questions = Question.objects.filter(
            session=session,
            node=current_node
        ).order_by('created_at')
        
        previous_answers = [
            q.answer for q in previous_questions
            if hasattr(q, 'answer')
        ]
        
        # 深掘りレベルを決定
        depth_level = len(previous_answers) + 1
        
        # 最大深掘りレベルをチェック
        max_depth = settings.INTERVIEW_CONFIG.get('SOCRATIC_DEPTH_LEVELS', 3)
        
        if depth_level > max_depth:
            # 次のトピックに移動
            return self._move_to_next_topic(session)
        
        # 質問を生成
        question = self.generator.generate_question(
            current_node, session, depth_level, previous_answers
        )
        
        return question
    
    def _move_to_next_topic(self, session):
        """次のトピックに移動"""
        from interview_session.services import SessionManager
        
        session_manager = SessionManager()
        next_topic = session_manager.select_next_topic(session)
        
        if next_topic:
            session.current_node = next_topic
            session.save()
            
            # 新しいトピックの最初の質問を生成
            return self.generator.generate_question(next_topic, session, 1)
        
        return None
    
    def should_continue_questioning(self, session):
        """質問を続けるべきかどうかを判定"""
        # すべてのノードの理解度をチェック
        if session.material.root_node:
            all_nodes = session.material.root_node.get_descendants()
            avg_understanding = sum(node.understanding_score for node in all_nodes) / len(all_nodes)
            
            # 平均理解度が閾値を超えたら終了
            return avg_understanding < 0.8
        
        return True
