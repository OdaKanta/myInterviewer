import sys
from interview_session.models import InterviewSession
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import KnowledgeNode, DocumentChunk, LearningMaterial
from .serializers import KnowledgeNodeSerializer, DocumentChunkSerializer
from .services import InterviewOrchestrator

class KnowledgeNodeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = KnowledgeNode.objects.all()
    serializer_class = KnowledgeNodeSerializer
    
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """知識ツリーの階層構造を取得"""
        material_id = request.query_params.get('material_id')
        
        if material_id:
            try:
                material = LearningMaterial.objects.get(id=material_id)
                if material.root_node:
                    serializer = self.get_serializer(material.root_node)
                    return Response(serializer.data)
                else:
                    return Response(
                        {'message': 'この教材はまだ処理されていません。'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            except LearningMaterial.DoesNotExist:
                return Response(
                    {'error': '指定された教材が見つかりません。'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # ルートノード（parent=None）を取得
        root_nodes = KnowledgeNode.objects.filter(parent=None)
        serializer = self.get_serializer(root_nodes, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def interview_next_step(self, request):
        """
        インタビューの次のステップを決定する「司令塔」。
        フローチャートのロジックを実行します。
        """

        # --- 1. JavaScript（explanation-phase.js / questioning-phase.js）から今の状況を受け取る ---
        session_id = request.data.get('session_id') # セッション ID
        material_id = request.data.get('material_id') # 教材 ID
        user_answer = request.data.get('user_answer') # ユーザーの回答
        current_question = request.data.get('interview_next_question', '')  # 評価対象の質問文（インタビュー開始時は 空）
        current_node_id = request.data.get('current_node_id', None) # 現在のノード（インタビュー開始時は None）
        uncleared_node_ids = request.data.get('uncleared_node_ids', None) # 未訪問リスト（インタビュー開始時は None）
        socratic_stage = int(request.data.get('socratic_stage', -1)) # ソクラテス式の質問の段階（インタビュー開始時は -1）
        consec_fail_count = int(request.data.get('consec_fail_count', -1)) # 同じノードでの質問回数（インタビュー開始時は -1）
        full_history = request.data.get('interview_session_history', []) # 質問応答の履歴（インタビュー開始時は 空）
        
        print("# JavaScript（ブラウザ側）から学習者の回答を受け取りました", file=sys.stderr)
        print("# 学習者の回答:", user_answer, file=sys.stderr)
        print("", file=sys.stderr)

        try:
            # --- 2. 実際の「次、どうするか？」の判断は services.py に任せる ---
            orchestrator = InterviewOrchestrator(material_id) # ここで InterviewOrchestrator の __init_() が呼ばれる
            root_node = orchestrator.material.root_node # material_id とそれに対応する root_node は一対一

            # [A] current_node_id が None の場合は「説明フェーズ」 からの最初の呼び出し
            if current_node_id is None:
                print("# ルートノード:", file=sys.stderr)
                print("  title:", root_node.title, file=sys.stderr)
                print("  description:", root_node.description, file=sys.stderr)
                print("=================================", file=sys.stderr)

                # セッションのステータスを 'questioning' に更新
                try:
                    session = InterviewSession.objects.get(id=session_id)
                    if session.status == 'explaining':
                        session.status = 'questioning'
                        session.save()
                except InterviewSession.DoesNotExist:
                    return Response({'error': '指定されたセッションが見つかりません'}, status=status.HTTP_404_NOT_FOUND)
                
                # これから訪問すべき全ノードのIDリストを作成
                all_descendants_nodes = root_node.get_descendants()
                all_node_ids = [node.id for node in all_descendants_nodes] + [root_node.id] # まだ質問してない項目のリスト
                # 次の行動を決定（現在地は根ノード）
                result_data = orchestrator.determine_next_step(user_answer, current_node_id=root_node.id, uncleared_node_ids=all_node_ids, consec_fail_count=0, socratic_stage=1)
            
            # [B] current_node_id が 存在する場合は「質問フェーズ」 のループ中の呼び出し
            else:
                if not uncleared_node_ids:
                    print("この処理は実行されないはず", file=sys.stderr)
                
                # 次の行動を決定
                result_data = orchestrator.determine_next_step(user_answer, current_node_id, uncleared_node_ids, current_question=current_question, consec_fail_count=int(consec_fail_count), socratic_stage=int(socratic_stage), full_history=full_history)
            
            # 決定した結果をフロントエンド（explanation_phase.js / questioning-phase.js）に返す
            return Response(result_data)

        except (LearningMaterial.DoesNotExist, KnowledgeNode.DoesNotExist):
            return Response(
                {'error': '指定された教材またはノードが見つかりません'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'処理中に予期せぬエラーが発生しました: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DocumentChunkViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DocumentChunk.objects.all()
    serializer_class = DocumentChunkSerializer
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """類似チャンクを検索"""
        query = request.query_params.get('query')
        node_id = request.query_params.get('node_id')
        
        if node_id:
            # 指定されたノードに関連するチャンクを取得
            try:
                node = KnowledgeNode.objects.get(id=node_id)
                chunks = node.chunks.all()
                serializer = self.get_serializer(chunks, many=True)
                return Response(serializer.data)
            except KnowledgeNode.DoesNotExist:
                return Response(
                    {'error': '指定されたノードが見つかりません。'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # 全チャンクを返す（実際の実装では類似検索を行う）
        chunks = DocumentChunk.objects.all()[:10]
        serializer = self.get_serializer(chunks, many=True)
        return Response(serializer.data)
