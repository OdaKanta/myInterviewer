import os
import sys
import time
import json
import chromadb
import base64
import fitz  # PyMuPDF
from celery import shared_task, group, chord, chain
from sentence_transformers import SentenceTransformer
from django.conf import settings
from django.core.files.storage import default_storage
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import BaseModel
from typing import List
from .models import LearningMaterial, DocumentChunk, KnowledgeNode


class KGNode(BaseModel):
    """知識ツリーのノードを表すPydanticモデル"""
    title: str
    description: str
    related_chunks: List[int] = []
    children: List['KGNode'] = []

# グローバル関数として定義
@shared_task
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((Exception,))
)
def analyze_page_task(page_number, image_data):
    """GPT-4oを使用してページ画像を包括的に分析（リトライ機能付き）"""
    # 画像データをbase64エンコード
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # GPT-4oで詳細分析
    response = openai_client.chat.completions.create(
        model= "gpt-4o-2024-11-20",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""この講義資料のページの内容を詳細に分析し、以下の情報を含めて説明してください：
1. テキスト: ページに書かれているすべてのテキストを正確に抽出
2. 図表・グラフ: 存在する場合、内容と数値データを詳細に説明
3. 画像・イラスト: 存在する場合、視覚的要素の内容と意味
4. 数式・記号: 数学的表現や特殊記号があれば正確に記録
"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        max_tokens=16000,
        temperature=0.0
    )
    return {"page_number": page_number, "content": response.choices[0].message.content}

@shared_task
def collect_pages_result(pages_results):
    return sorted(pages_results, key=lambda x: x['page_number'])

class PDFProcessor:
    """PDFからテキストを抽出し、チャンク化する"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-3-large"

    def _render_page_to_image(self, page):
        """ページを高解像度画像としてレンダリング"""
        mat = fitz.Matrix(2.0, 2.0)  # 2倍ズーム for better quality
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")

    @shared_task # 新しい Celery タスクとして定義
    def chunk_and_embed_task(pages_text, material_id):
        """ページテキストをチャンク化し、Embeddingを生成し、DBに保存する"""
        # print("[DEBUG] pages_text:", pages_text, file=sys.stderr)
        processor = PDFProcessor() # インスタンスをタスク内で再生成
        
        # 1. テキストをチャンク化
        chunks = processor.chunk_text(pages_text)
        # print("[DEBUG] chunks:", chunks, file=sys.stderr)
        # 2. 埋め込みベクトルを生成
        chunks_with_embeddings = processor.generate_embeddings(chunks)
        
        # 3. データベースにチャンクを保存
        material = LearningMaterial.objects.get(id=material_id)
        for chunk_data in chunks_with_embeddings:
            DocumentChunk.objects.create(
                learning_material=material,
                content=chunk_data['content'],
                embedding=chunk_data['embedding'],
                page_number=chunk_data['page_number'],
                chunk_index=chunk_data['chunk_index']
            )
            
        return material_id, chunks_with_embeddings # 次のタスク（generate_knowledge_tree_task() の result_tuple）に必要な情報を返す

    def chunk_text(self, pages_text, chunk_size=500, overlap=0):
        """テキストをチャンク化"""
        chunks = []
        
        for page_data in pages_text:
            page_number = page_data['page_number']
            content = page_data['content']
            
            # 文章を指定サイズでチャンク化
            words = content.split()
            for i in range(0, len(words), chunk_size - overlap):
                chunk_words = words[i:i + chunk_size]
                chunk_text = ' '.join(chunk_words)
                
                if chunk_text.strip():
                    chunks.append({
                        'page_number': page_number,
                        'chunk_index': len(chunks),
                        'content': chunk_text
                    })
        
        return chunks

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    def _get_embeddings_batch(self, contents):
        """複数のコンテンツに対してEmbeddingを一括取得（リトライ付き）"""
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=contents  # リストで複数テキストを送信
        )
        return [item.embedding for item in response.data]

    def generate_embeddings(self, chunks):
        """チャンクの埋め込みベクトルを生成（OpenAI Embeddingを使用、バッチ処理）"""
        # すべてのチャンクのコンテンツを抽出
        contents = [chunk['content'] for chunk in chunks]
        
        # 一括でEmbeddingを取得
        embeddings = self._get_embeddings_batch(contents)
        
        # 各チャンクにEmbeddingを割り当て
        for i, chunk in enumerate(chunks):
            chunk['embedding'] = embeddings[i]
        
        return chunks


class KnowledgeTreeGenerator:
    """LLMを使用して知識ツリーを生成"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o-2024-11-20"

    def generate_knowledge_tree(self, chunks, material_title):
        """チャンクから知識ツリーを生成"""
        # チャンクの内容を結合
        full_content = '\n\n'.join([f"chunk_index: {chunk['chunk_index']}, content: {chunk['content']}" for chunk in chunks])
        print("[DEBUG] full_content:", full_content, file=sys.stderr)
        prompt = f"""
        あなたは、提供された講義資料の内容を、学習者が理解するための非常に深く階層化された深さ6以上の巨大知識ツリー（KGNode）に変換する専門家です。

        ■ 要件:
        [A] ツリーの構造
        - 深さ: ルートを含め可能な限り深く掘り下げよ。最低でも6階層まで深くせよ。ツリーは可能な限り深くせよ。
        - 幅: 各親ノードは可能な限り細分化し、ノードの総数を限りなく増やしなさい。
        - バランス: 知識を不必要に一方向に深くせず、横に広げるように構造を最適化せよ。可能な限り細分化することにより、大量のノードを生成せよ。
        - 学習内容とは直接関係のない問題部分などはノードにしてはならない。
        - 講義資料の冒頭に存在する目次からは情報を使用してはならない。
        - ノードとして抽出する学習項目は、トピックとしてリストアップされているだけでなく、そのトピックが資料中に図や具体的な説明などにより言及されているものに限定してください。
        
        [B] ルートノード
        - title: 教材全体の内容を最も具体的に表す主題を一言で記述せよ。**大学名、科目名、年度、知識ツリー、講義内容の整理、本教材の目的のようなメタ情報は絶対に含めてはいけない。
        - description: 空にせよ。
        - related_chunks: 空にせよ。

        [C] ノード
        - title: 各ノードのタイトルは具体的な事項かつ簡潔にせよ。
        - description: 講義資料の内容のみを反映させ、なるべく詳細な日本語文（2文以上）で説明せよ。
        - related_chunks: 各ノードに関連するチャンクの chunk_index のリスト。
        -【重要】「～について解説」や「～について記述」、「～を説明」のような語尾は厳禁。講義資料に書かれている内容だけを述べよ。

        ■ 教材内容:
        {full_content}
        """
        response = self.openai_client.beta.chat.completions.parse(
            model=self.model,
            response_format=KGNode,
            messages=[
                {"role": "system", "content": "あなたは教育専門家です。提供された講義資料の内容のみを扱い、抽象的なメタ情報を含まない、具体的な主題を記述した深さ6以上の巨大ツリー構造ノード（KGNode）を生成してください。各ノードの説明文は、「～について解説」や「～について記述」、「～を説明」のような語尾ではなく、単に講義資料に書かれている内容だけを述べるだけにしなさい。また、各ノードのdescriptionは講義資料の内容に基づいて極力詳細にせよ（descriptionは必ず3文以上にせよ）。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        try:
            # Structured Outputsで解析されたKGNodeモデルを取得
            knowledge_tree = response.choices[0].message.parsed
            if knowledge_tree:
                # PydanticモデルをDictに変換（このdictが新しいルート構造となる）
                return knowledge_tree.model_dump()
            else:
                raise ValueError("Failed to parse knowledge tree")
        except Exception as e:
            # フォールバック: 簡単な構造を返す
            print(f"Knowledge tree generation error: {e}")
            return {
                "title": material_title,
                "description": "自動生成された知識ツリー",
                "children": []
            }
    
    def create_knowledge_nodes(self, tree_data, parent=None, level=0):
        """知識ツリーデータから再帰的にKnowledgeNodeを作成"""
        # orderが指定されていない場合は0をデフォルトとする
        order = tree_data.get('order', 0)
        
        node = KnowledgeNode.objects.create(
            title=tree_data['title'],
            description=tree_data['description'],
            parent=parent,
            level=level,
            order=order
        )
        node.related_chunks.set(tree_data.get('related_chunks', []))
        
        for i, child_data in enumerate(tree_data.get('children', [])):
            child_data['order'] = i
            self.create_knowledge_nodes(child_data, parent=node, level=level + 1)
        
        return node

@shared_task # 新しい Celery タスクとして定義
def generate_knowledge_tree_task(result_tuple):
    """知識ツリーを生成し、教材を更新する"""
    
    material_id, chunks_with_embeddings = result_tuple
    
    material = LearningMaterial.objects.get(id=material_id)
    tree_generator = KnowledgeTreeGenerator()
    
    # 知識ツリーを生成
    tree_data = tree_generator.generate_knowledge_tree(chunks_with_embeddings, material.title)
    print("[DEBUG] tree_data:", tree_data, file=sys.stderr)
    # 知識ノードを作成
    root_node = tree_generator.create_knowledge_nodes(tree_data)
    
    # 教材を更新
    material.root_node = root_node
    material.processed = True
    material.save()
    
    return material.id

class MaterialProcessor:
    """教材処理の統合クラス"""
    
    @shared_task # 外部からのトリガー用タスク
    def start_processing_workflow(material_id):
        """教材処理の非同期ワークフロー全体を開始する"""
        
        # 1. PDFから画像抽出（この部分はまだ同期的にメインプロセスで実行）
        try:
            material = LearningMaterial.objects.get(id=material_id)
            file_path = material.file_path.path
            
            # PDFページを画像化
            pages = []
            doc = fitz.open(file_path)
            processor = PDFProcessor()
            for page_num, page in enumerate(doc, start=1):
                img_data = processor._render_page_to_image(page)
                pages.append({'page_number': page_num, 'image': img_data})
            doc.close()
            
        except Exception as e:
            # 処理失敗時のログと処理
            print(f"Error preparing material {material_id}: {e}", file=sys.stderr)
            raise e

        # 2. Celery ワークフローの構築
        # Step A: ページ分析 (並列) -> Step B: 結果収集 (コールバック)
        page_analysis_group = group(analyze_page_task.s(page['page_number'], page['image']) for page in pages) # 各ページに対して非同期タスクを作成して group でまとめて並列処理
        
        # Step C: チャンク化とEmbedding生成 (material_id を引数に追加)
        chunk_embed_task = PDFProcessor.chunk_and_embed_task.s(material_id) 
        
        # Step D: 知識ツリー生成とDB更新
        tree_gen_task = generate_knowledge_tree_task.s()

        # 3. ワークフローの実行 (chord -> chain)
        workflow = chain(
            chord(page_analysis_group, collect_pages_result.s()), # A -> B (Pages_Text を生成)
            chunk_embed_task,                                     # B の結果を C に渡す (Chunks_With_Embeddings を生成)
            tree_gen_task                                         # C の結果を D に渡す (最終更新)
        )
        
        # ワークフローを開始
        workflow.apply_async()
        
        return f"Material {material_id} processed successfully"

###
### 新しく追加しました！！views.py で使用するクラスです！！
###
class InterviewOrchestrator:
    """インタビューの進行を管理するクラス"""
    
    MAX_SOCRATIC_STAGES = 3 # ソクラテス式質問の最大段階数

    def __init__(self, material_id):
        try:
            self.material = LearningMaterial.objects.get(id=material_id)
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = "gpt-4o-2024-11-20"
        except LearningMaterial.DoesNotExist:
            raise ValueError("指定された教材が見つかりません")
    
    def determine_next_step(self, user_answer, current_node_id, uncleared_node_ids, current_question=None, consec_fail_count=0, socratic_stage=1, full_history=[]):
        
        current_node = KnowledgeNode.objects.get(id=current_node_id)

        if current_question is None: # 初回は回答評価はせず、回答に関連するノードに進む処理だけを行う
            print("# 初回", file=sys.stderr)
            uncleared_node_ids.remove(current_node.id) # ルートノードは真っ先にクリアにしてしまう
            next_node = self._shift_next_node(user_answer, current_node, uncleared_node_ids, full_history)
        else: # 初回以外はまず回答を評価する
            evaluation = self._evaluate_answer(current_node, current_question, user_answer)
            if evaluation >= 3: # 5段階評価で3以上であればリメディアル終了、または次のソクラテス段階に進む、またはすでに最終段階であればそのノードはクリアして次のノードに移動
                if consec_fail_count > 0: #（段階を問わず）リメディアル質問に正解した場合
                    print(f"# 評価値: {evaluation}（リメディアルから脱出）", file=sys.stderr)
                    consec_fail_count = 0 # リセット
                    next_node = current_node # ノードはそのまま
                elif socratic_stage < self.MAX_SOCRATIC_STAGES: # 次のソクラテス段階に進む場合
                    print(f"# 評価値: {evaluation}（次の段階へ進む）", file=sys.stderr)
                    consec_fail_count = 0 # リセット
                    socratic_stage += 1 # 次の段階へ
                    next_node = current_node # ノードはそのまま
                else: # 最終段階を終了する場合（ノードをクリア）
                    print(f"# 評価値: {evaluation}（ノードをクリアして次のノードへ進む）", file=sys.stderr)
                    consec_fail_count = 0 # リセット
                    socratic_stage = 1 # リセット
                    if current_node.id in uncleared_node_ids:
                        uncleared_node_ids.remove(current_node.id)
                    print("[DEBUG] 省略審査開始", file=sys.stderr)
                    while True: # スキップ可能な限り（未クリアの子ノードの数が 1 であり、かつそのノードの内容をすでに発話している場合）はどんどん先に進む
                        print("")
                        uncleared_child = []
                        for child in current_node.children.all():
                            if child.id in uncleared_node_ids:
                                uncleared_child.append(child)
                        print("[DEBUG] 省略前の現在地:", current_node.title, "( 未クリアの子ノード数:", len(uncleared_child), ")", file=sys.stderr)
                        if len(uncleared_child) == 1:
                            child = current_node.children.get(id=uncleared_child[0].id)
                            if self._can_skip_child(child, full_history):
                                # 子ノードをクリアにして現在地を進める
                                uncleared_node_ids.remove(child.id)
                                print("# 省略", child.title, file=sys.stderr)
                                current_node = child
                                print("[DEBUG] 省略後の現在地:", current_node.title, file=sys.stderr)
                            else:
                                break
                        else:
                            break
                    print("[DEBUG] 省略審査終了", file=sys.stderr)
                    
                    print("[DEBUG] 剪定審査開始", file=sys.stderr)
                    self._skip_sibling(current_node, uncleared_node_ids, full_history)
                    print("[DEBUG] 剪定審査終了", file=sys.stderr)
                    next_node = self._shift_next_node(user_answer, current_node, uncleared_node_ids, full_history) # 全ノードクリアした場合は None が返る
                if next_node is None: # ツリーをすべて網羅した場合
                    print("# すべてクリア", file=sys.stderr)
                    return {'status': 'interview_completed'}
            else: # 評価値が3未満なら同じノードで同じ段階のリメディアル質問
                print(f"# 評価値: {evaluation}（失敗）", file=sys.stderr)
                consec_fail_count += 1
                next_node = current_node
        print("# 現在地:", next_node.title, "/", next_node.description, file=sys.stderr)
        
        # 質問生成
        next_question = self._generate_question(next_node, socratic_stage, consec_fail_count, full_history)
        print(f"# 質問（第{socratic_stage}段階 - 連続失敗回数: {consec_fail_count}）: {next_question}", file=sys.stderr)
        return {
            'interview_next_question': next_question,
            'next_node_id': next_node.id if next_node else None,
            'uncleared_node_ids': uncleared_node_ids,
            'status': 'interview_in_progress',
            'consec_fail_count': consec_fail_count,
            'socratic_stage': socratic_stage
        }
    
    # 次に移動するノードを見つける関数（見つからなければインタビュー終了）
    def _shift_next_node(self, user_answer, current_node, uncleared_node_ids, full_history):
        next_node = self._find_matching_uncleared_child(user_answer, current_node, uncleared_node_ids) # 直下の未クリアの子ノードの中から関連するノードがあれば、最もマッチするものを探す
        if not next_node: # そもそも子ノードが存在しない葉ノードにいる場合や、子ノードに未クリアノードがもうない場合は None が返ってくる
            next_node = self._find_uncleared_other_node(user_answer, current_node, uncleared_node_ids, full_history) # ノードを再帰的に登って（根ノードに到達したら下って）未クリアの子ノードを見つける
        if not next_node: # 全ノードクリア済みの場合、_find_uncleared_other_node から None が返される
            return None
        return next_node

    # 未クリアで（current_node は参照渡しなので関数内で変更されうる）
    def _can_skip_child(self, child: KnowledgeNode, full_history: list):
        history_text = ""
        for history in full_history:
            history_text += f"  [Q] {history['question']}\n  [A] {history['answer']}"
        
        prompt = f"""
        あなたは {child.get_root().title} の専門家です。学習者の回答履歴に基づき、{child.title} にすでに言及されているか、そうでないかを判断してください。

        ■ 回答履歴:
        {history_text}
        
        ■ トピック:
        {child.title}: {child.description}
                
        ■ 判定基準
        - 回答履歴が当該トピックの説明に言及されている場合 → true
        - 触れていない場合 → false

        ■ 出力形式 (JSON):
        {{"is_sufficient": true または false}}
        """
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "あなたは回答履歴を分析し、トピックに言及されているかをtrue/falseで返します。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        result = json.loads(response.choices[0].message.content)
        print("       ", result['is_sufficient'], file=sys.stderr)
        return result['is_sufficient']

    # 未クリアで葉ノードである兄弟ノードで枝刈りできるノードは枝刈り
    def _skip_sibling(self, current_node: KnowledgeNode, uncleared_node_ids: list, full_history: list):
        uncleared_sibling_nodes = [node for node in current_node.get_siblings() if node.id in uncleared_node_ids and not node.children.exists()] # 未クリアの兄弟ノードで葉ノードである（子を持たない）ノードのリスト
        if not uncleared_sibling_nodes:
            return
        nodes_to_compare = "\n".join([f"- ID {node.id}: {node.title} / {node.description}" for node in uncleared_sibling_nodes])

        history_text = ""
        for history in full_history:
            history_text += f"  [Q] {history['question']}\n  [A] {history['answer']}"
        
        prompt = f"""
        あなたは知識の剪定師です。学習者の回答履歴に基づき、以下のトピックのうち、すでに明言されているものがあればその ID を列挙してください。

        ■ 回答履歴:
        {history_text}
        
        ■ トピック:
        {nodes_to_compare}

        ■ 要件:
        1. 回答履歴と、各トピックの「説明」を比較し、そのトピックの内容がすでに学習者によって十分に言及され、カバーされていると判断されるノードのIDをすべてJSON配列で返してください。
        2. 完全にカバーされていない場合は、IDを返さないでください。
        
        ■ 出力形式 (JSON):
        {{"pruned_ids": [10, 15, 22, ...]}}
        """
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "あなたは回答履歴を分析し、カバー済みのトピックIDのみをJSON配列で返します。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        result = json.loads(response.choices[0].message.content)
        pruned_ids = result.get('pruned_ids', [])

        for node_id in pruned_ids:
            uncleared_node_ids.remove(node_id)
            print("# 剪定", KnowledgeNode.objects.get(id=node_id).title, file=sys.stderr)

    # 回答をノードと照らし合わせて評価する関数
    def _evaluate_answer(self, current_node: KnowledgeNode, question_text: str, answer_text: str) -> int:
        """
        LLMを使用して、質問に対する回答を評価する
        """
        prompt = f"""
        あなたは {current_node.get_root().title} の専門家です。{current_node.title} に関する質問に対する学習者の回答を評価し、5段階評価（1~5）してください。

        ■ 質問
        {question_text}

        ■ 学習者の回答
        {answer_text}

        ■ 5段階評価: 1（質問と無関係の回答；または誤った回答）～5（質問に対する回答として適切）
        
        ■ 出力形式 (JSON): {{"evaluation": (int)}}
        """
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "あなたは回答を評価する教育専門家です。質問内容に忠実な回答かを5段階評価してください。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        result = json.loads(response.choices[0].message.content)
        return int(result.get('evaluation', 0))

    ###
    ### 学習者の回答と最も関連する未クリアの子孫ノードをみつけて、そのノードが存在する方向にある未クリアの子ノードを返す関数！！！
    ###
    def _find_matching_uncleared_child(self, user_answer: str, current_node: KnowledgeNode, uncleared_node_ids: list) -> KnowledgeNode:
        """
        LLM を使用して、学習者の回答が current_node 以下のどの子孫ノードに最も関連しているかを判断し、そのノードへの通り道に存在する子ノードを返す
        """
        # current_node 直下の未クリアの子ノードの ID を取得
        children = [child for child in current_node.children.all() if child.id in uncleared_node_ids] # 'knowledge_tree/models.py' の related_name='children' を使用している！
        if not children: # 未クリアの子ノードがない場合は、None を返す
            return None
        if len(children) == 1: # 未クリアの子ノードが 1 つしかない場合は、そのノードを返す
            return children[0]
        
        # current_node 以下の未クリアの子孫ノードの ID を取得
        descendants = [descendant for descendant in current_node.get_descendants() if descendant.id in uncleared_node_ids]

        # LLM の性能を最大限に引き出すために、トーナメント式に関連度が最大の未クリアの子孫ノードを見つけ出す
        survivor = descendants.copy()
        while len(survivor) > 1:
            winners = []
            for i in range(0, len(survivor), 2): # 2 つずつペアをつくる
                if i+1 == len(survivor): # 奇数のためペアをつくれない余りが生じた場合は不戦勝とする
                    winners.append(survivor[i])
                else:
                    winners.append(self._compare_relevance(user_answer, survivor[i], survivor[i+1]))
            survivor = winners.copy()
        matched_node = survivor[0]
        if matched_node in children: # 直下の子ノードとマッチした場合
            return matched_node
        else:
            for ancestor in matched_node.get_ancestors():
                if ancestor.parent_id is None:
                    print("やばい", file=sys.stderr) # 根ノードに達してるやん
                if ancestor.parent_id == current_node.id:
                    return ancestor

    # 与えられた 2 つのノードのうち、学習者の回答により関連するほうを返す
    def _compare_relevance(self, user_answer: str, a: KnowledgeNode, b: KnowledgeNode) -> KnowledgeNode:
        prompt = f"""
        あなたは学習者の回答を分析する専門家です。以下の学習者の回答に対し、オプションAとオプションBのどちらが関連性が高いか判断してください。

        ■ 学習者の回答: {user_answer}

        ■ オプションA
        タイトル: {a.title}
        説明: {a.description}

        ■ オプションB
        タイトル: {b.title}
        説明: {b.description}

        ■ 出力形式 (JSON):
        {{"option": (A or B)}}
        """
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "あなたは、提示された2つのオプションを比較し、学習者の回答と関連性の高いほうの選択肢をJSONで返します。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0 # 比較・分類タスクは 0.0 が望ましい
        )
        result = json.loads(response.choices[0].message.content)
        if result['option'] == 'A':
            print(f"- {a.title} > {b.title}", file=sys.stderr)
        elif result['option'] == 'B':
            print(f"- {a.title} < {b.title}", file=sys.stderr)
        else:
            print("- やばい", file=sys.stderr)
        return a if result['option'] == 'A' else b

    ###
    ### 子孫がすべてクリアされたかチェックする関数
    ###
    def _is_subtree_cleared(self, current_node: KnowledgeNode, uncleared_node_ids: list) -> bool:
        """
        指定されたノード(current_node) の「子孫」が「未クリアリスト(uncleared_node_ids)」に残っていないことをチェックする
        """
        descendants = current_node.get_descendants()
        if not descendants:
            return True # そもそも子孫がいない（葉ノード）場合は、常に「クリア済み」

        for descendant in descendants:
            if descendant.id in uncleared_node_ids:
                return False # 1つでも未クリアの子孫が見つかったら、即座に False (まだクリアしていない子孫が存在する)
        return True # 未クリアの子孫が 1 人もいなかった = サブツリーはすべてクリア済み

    ###
    ### ノードを再帰的に登って（根ノードに到達したら下って）未クリアの子ノードを見つける関数！！！
    ###
    def _find_uncleared_other_node(self, user_answer: str, current_node: KnowledgeNode, uncleared_node_ids: list, full_history: list) -> KnowledgeNode:
        """
        現在のノードから親ノードをたどり、未クリアの子ノードを持つ祖先を見つけたら、そこから次に進むべきノードを返す。
        """
        while current_node: # 未クリアの子ノードをもつノード、または根ノードに到達するまでループ（ただし、根ノードは含む）
            if self._is_subtree_cleared(current_node, uncleared_node_ids):
                if current_node.id in uncleared_node_ids:
                    uncleared_node_ids.remove(current_node.id) # サブツリーが完了している場合、このノードをクリアする
                current_node = current_node.parent # 親ノードに移動
                if current_node is None: # 根ノードまでクリアし、current_node が None になった場合
                    return None # すべてのノードがクリアになったのでインタビュー終了
            else: # 未クリアの子孫がいた場合
                break
        next_node = self._find_matching_uncleared_child(user_answer, current_node, uncleared_node_ids) # 直下の未クリアの子ノードの中から最も関連するノードを探す
        print("[DEBUG] _find_uncleared_other_node() 内部", file=sys.stderr)
        print("[DEBUG] 省略審査開始", file=sys.stderr)
        while True: # スキップ可能な限り（未クリアの子ノードの数が 1 であり、かつそのノードの内容をすでに発話している場合）はどんどん先に進む
            print("")
            print("[DEBUG] 省略前の現在地:", next_node.title, file=sys.stderr)
            uncleared_child = []
            for child in next_node.children.all():
                if child.id in uncleared_node_ids:
                    uncleared_child.append(child)
            print("[DEBUG] 未クリアの子ノード数:", len(uncleared_child), file=sys.stderr)
            if len(uncleared_child) == 1:
                child = next_node.children.get(id=uncleared_child[0].id)
                if self._can_skip_child(child, full_history):
                    # 子ノードをクリアにして現在地を進める
                    uncleared_node_ids.remove(child.id)
                    print("# 省略", child.title, file=sys.stderr)
                    next_node = child
                    print("[DEBUG] 省略後の現在地:", next_node.title, file=sys.stderr)
                else:
                    break
            else:
                break
        print("[DEBUG] 省略審査終了", file=sys.stderr)
        return next_node

    ###
    ### ソクラテス式の質問を生成する関数！！！
    ###
    def _generate_question(self, current_node, socratic_stage, consec_fail_count, full_history):
        lecture_content = ""
        if not current_node.children.exists(): # 葉ノードであれば、そのノードに関連するチャンクから質問を生成（具体的な内容が講義資料に書いてあるはずだから）
            print("[DEBUG] 葉ノードに到達したので講義資料の具体的な記述から質問を生成", file=sys.stderr)
            related_chunks = current_node.chunks.all() # 関連するチャンク（knowledge_tree/models.py の DocumentChunk モデルへの逆参照）
            print("     >> 関連するチャンク:", related_chunks, file=sys.stderr)
            if related_chunks:
                lecture_content = "■ 講義資料の抜粋:\n"
                for chunk in related_chunks:
                    lecture_content += f"- {chunk.content}\n"
            print("       ", lecture_content, file=sys.stderr)
            lecture_content += "# 指示: 必ず上記の「講義資料の抜粋」に含まれる情報だけを元に質問を作成してください。"
        
        if socratic_stage == 1:
            system_message = "提供された資料に基づき、トピックの定義や主要な事実、専門用語を答えさせる質問を作成してください。"
            question_type = "定義、主要な事実、専門用語を問う質問"
        elif socratic_stage == 2:
            system_message = "提供された資料に基づき、トピックの理由、原因、または動作原理を問う質問を作成してください。"
            question_type = "理由・原因、動作原理を問う質問"
        elif socratic_stage == 3:
            system_message = "提供された資料に基づき、トピックの応用、関連性、または一般化を問う質問を作成してください。"
            question_type = "応用やより一般的な質問"
        else:
            print("やばい", file=sys.stderr)
        
        # このノードでの履歴だけを取り出す  
        node_history = ""
        for history in full_history:
            if history['node_id'] == current_node.id:
                node_history += f"\n  [Q] {history['question']}\n  [A] {history['answer']}"

        print('================================================================================', file=sys.stderr)
        print("# このノードでの質問応答履歴:", node_history, file=sys.stderr)
        print('================================================================================', file=sys.stderr)

        prompt = f"""
        あなたは {current_node.get_root().title} の専門家です。以下の情報に基づいて {current_node.title} に関する {question_type} を生成してください。特に、これまでの質問応答の流れを意識した質問を生成してください。

        ■ 概要: {current_node.description}
        
        {lecture_content}

        ■ これまでの質問応答:
        {node_history}

        ■ 重要な指示:
        - 質問事項は必ず1つだけに絞ってください。
        - 必要に応じて、直前の学習者の回答に対する一声を入れても構いません。
        - 過去、特に直前のやり取りに基づいた応答にしてください。
        - これまでの質問と同じ質問は絶対にしないでください。
        - 質問文を囲む鍵括弧は不要です。
        """
        if consec_fail_count == 0: # 前回の回答に成功した場合
            system_message += f"\nあなたは教育専門家です。過去、特に直前のやり取りに基づいた質問を生成してください。"
        else: # 前回同じ段階でいまいちな回答だった場合
            system_message += f"\nあなたは教育専門家です。学習者は {consec_fail_count} 回連続で回答に失敗しています。過去の質問とは「異なる視点」や「より簡単なレベル」の質問を生成してください。ただし、過去、特に直前のやり取りに基づいた応答にしてください。"
        
        # AIに質問生成を依頼
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()