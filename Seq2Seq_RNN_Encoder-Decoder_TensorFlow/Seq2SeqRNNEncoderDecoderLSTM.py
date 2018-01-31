# -*- coding:utf-8 -*-
# Anaconda 5.0.1 環境 (TensorFlow インストール済み)

"""
    更新情報
    [17/12/14] : 新規作成
    [18/01/31] : クラス名（ファイル名）を RecurrectNNEncoderDecoderEmbeddingLSTM → Seq2SeqRNNEncoderDecoderLSTM に変更
               : RecurrectNNEncoderDecoderLSTM クラスの継承取りやめ
    [xx/xx/xx] :

"""

import numpy

# TensorFlow ライブラリ
import tensorflow as tf
from tensorflow.python.framework import ops

# scikit-learn ライブラリ
from sklearn.utils import shuffle

# 自作クラス
from NeuralNetworkBase import NeuralNetworkBase    # 親クラス

import NNActivation
from NNActivation import NNActivation               # ニューラルネットワークの活性化関数を表すクラス
from NNActivation import Sigmoid
from NNActivation import Relu
from NNActivation import Softmax

import NNLoss                                       # ニューラルネットワークの損失関数を表すクラス

import NNOptimizer                                  # ニューラルネットワークの最適化アルゴリズム Optimizer を表すクラス

class Seq2SeqRNNEncoderDecoderLSTM( NeuralNetworkBase ):
    """
    LSTM による RNN Encoder-Decoder を表すクラス.
    TensorFlow での RNN Encoder-Decoder の処理をクラス（任意の層に DNN 化可能な柔軟なクラス）でラッピングし、
    scikit-learn ライブラリの classifier, estimator とインターフェイスを共通化することで、
    scikit-learn ライブラリとの互換性のある自作クラス
    ------------------------------------------------------------------------------------------------
    [public] public アクセス可能なインスタスンス変数には, 便宜上変数名の最後にアンダースコア _ を付ける.
        _n_inputLayer : int
            入力層のノード数
        _n_hiddenLayer : int
            隠れ層のノード数
        _n_outputLayer : int
            出力層のノード数

        _n_in_sequence_encoder : int
            時系列データを区切った Encoder の各シークエンスの長さ（サイズ）
        _n_in_sequence_decoder : int
            時系列データを区切った Decoder の各シークエンスの長さ（サイズ）

        _rnn_cells_encoder : list <LSTMCell クラスのオブジェクト> <tf.Tensor 'RNN-LSTM/RNN-LSTM/lstm_cell>
            RNN Encoder-Decoder の Encoder 構造を提供する cell のリスト
            この `cell` は、内部（プロパティ）で state（隠れ層の状態）を保持しており、
            これを次の時間の隠れ層に順々に渡していくことで、時間軸の逆伝搬を実現する。
        _rnn_states_encoder : list <Tensor>
            Encoder の cell の状態のリスト
        _rnn_cells_decoder : lsit <LSTMCell クラスのオブジェクト> <tf.Tensor 'RNN-LSTM/RNN-LSTM/lstm_cell>
            RNN Encoder-Decoder の Decoder 構造を提供する cell のリスト
        _rnn_states_decoder : list <Tensor>
            Decoder の cell の状態のリスト

        _weights : list <Variable>
            モデルの各層の重みの Variable からなる list
        _biases : list <Variable>
            モデルの各層のバイアス項の  Variable からなる list

        _epochs : int
            エポック数（トレーニング回数）
        _batch_size : int
            ミニバッチ学習でのバッチサイズ
        _eval_step : int
            学習処理時に評価指数の算出処理を行う step 間隔

        _losses_train : list <float32>
            トレーニングデータでの損失関数の値の list

        _X_holder : placeholder
            入力層にデータを供給するための placeholder
        _t_holder : placeholder
            出力層に教師データを供給するための placeholder
        _dropout_holder : placeholder
            ドロップアウトしない確率 (1-p) にデータを供給するための placeholder
        _batch_size_holder : placeholder
            バッチサイズ _batch_size にデータを供給するための placeholder
            cell.zero_state(...) でバッチサイズを指定する必要があり、可変長に対応するために必要
        _bTraining_holder : placeholder
            トレーニング処理中か否かを表す placeholder

        _n_vocab : int
            vocabulary size （埋め込み行列の行数）

        _embedding_matrix_var : Variable
            埋め込み行列を表す Variable
        _embedding_lookup_op : Operator
            埋め込み検索演算を表す Operator

    [protedted] protedted な使用法を想定 

    [private] 変数名の前にダブルアンダースコア __ を付ける（Pythonルール）

    """
    def __init__( 
            self,
            session = tf.Session( config = tf.ConfigProto(log_device_placement=True) ),
            n_inputLayer = 1, n_hiddenLayer = 1, n_outputLayer = 1, 
            n_in_sequence_encoder = 25,
            n_in_sequence_decoder = 25,
            n_vocab = 500,
            epochs = 1000,
            batch_size = 10,
            eval_step = 1,
            save_step = 100
        ):
        """
        コンストラクタ（厳密にはイニシャライザ）
        """
        super().__init__( session )
        
        tf.set_random_seed(12)

        # 各パラメータの初期化
        self._n_inputLayer = n_inputLayer
        self._n_hiddenLayer = n_hiddenLayer
        self._n_outputLayer = n_outputLayer

        self._n_in_sequence_encoder = n_in_sequence_encoder
        self._n_in_sequence_decoder = n_in_sequence_decoder

        self._rnn_cells_encoder = []
        self._rnn_states_encoder = []
        self._rnn_cells_decoder = []
        self._rnn_states_decoder = []

        self._weights = []
        self._biases = []

        self._epochs = epochs
        self._batch_size = batch_size
        self._eval_step = eval_step        

        # evaluate 関連の初期化
        self._losses_train = []

        #
        self._n_vocab = n_vocab
        self._save_step = save_step

        self._embedding_matrix_var = None
        self._embedding_lookup_op = None

        # placeholder の初期化
        # shape の列（横方向）は、各層の次元（ユニット数）に対応させる。
        # shape の行は、None にして汎用性を確保
        self._X_holder = tf.placeholder( 
                             tf.int32, 
                             shape = [ None, self._n_in_sequence_encoder ],
                             name = "X_holder"
                         )

        self._t_holder = tf.placeholder( 
                             tf.int32, 
                             shape = [ None, self._n_in_sequence_decoder ],
                             name = "t_holder"
                         )

        self._dropout_holder = tf.placeholder( tf.float32, name = "dropout_holder" )
        self._batch_size_holder = tf.placeholder( tf.int32, shape=[], name = "batch_size_holder" )
        self._bTraining_holder = tf.placeholder( tf.bool, name = "bTraining_holder" )

        return

    def print( self, str):
        print( "---------------------------" )
        print( self )     
        super().print( str )

        print( self )

        print( "_session : ", self._session )
        print( "_init_var_op :\n", self._init_var_op )

        print( "_loss_op : ", self._loss_op )
        print( "_optimizer : ", self._optimizer )
        print( "_train_step : ", self._train_step )
        print( "_y_out_op : ", self._y_out_op )

        print( "_n_inputLayer : ", self._n_inputLayer )
        print( "_n_hiddenLayer : ", self._n_hiddenLayer )
        print( "_n_outputLayer : ", self._n_outputLayer )

        print( "_n_in_sequence_encoder :", self._n_in_sequence_encoder )
        print( "_n_in_sequence_decoder :", self._n_in_sequence_decoder )

        print( "_epoches : ", self._epochs )
        print( "_batch_size : ", self._batch_size )
        print( "_eval_step : ", self._eval_step )
        print( "_save_step : {}".format( self._save_step ) )

        print( "_n_vocab : {}".format( self._n_vocab ) )
        
        print( "_embedding_matrix_var : {}".format( self._embedding_matrix_var ) )
        print( "_embedding_lookup_op : {}".format( self._embedding_lookup_op ) )

        print( "_X_holder :", self._X_holder )
        print( "_t_holder :", self._t_holder )
        print( "_dropout_holder :", self._dropout_holder )
        print( "_batch_size_holder :", self._batch_size_holder )
        print( "_bTraing_holder :", self._bTraining_holder )

        print( "_rnn_cells_encoder : \n", self._rnn_cells_encoder )
        print( "_rnn_states_encoder : \n", self._rnn_states_encoder )
        print( "_rnn_cells_decoder : \n", self._rnn_cells_decoder )
        print( "_rnn_states_decoder : \n", self._rnn_states_decoder )

        print( "_weights : \n", self._weights )
        if( (self._session != None) and (self._init_var_op != None) ):
            print( self._session.run( self._weights ) )

        print( "_biases : \n", self._biases )
        if( (self._session != None) and (self._init_var_op != None) ):
            print( self._session.run( self._biases ) )

        print( "----------------------------------" )

        return


    def init_weight_variable( self, input_shape ):
        """
        重みの初期化を行う。
        重みは TensorFlow の Variable で定義することで、
        学習過程（最適化アルゴリズム Optimizer の session.run(...)）で自動的に TensorFlow により、変更される値となる。

        [Input]
            input_shape : [int,int]
                重みの Variable を初期化するための Tensor の形状

        [Output]
            正規分布に基づく乱数で初期化された重みの Variable 
            session.run(...) はされていない状態。
        """

        # ゼロで初期化すると、うまく重みの更新が出来ないので、正規分布に基づく乱数で初期化
        # tf.truncated_normal(...) : Tensor を正規分布なランダム値で初期化する
        init_tsr = tf.truncated_normal( shape = input_shape, stddev = 0.01 )

        # 重みの Variable
        weight_var = tf.Variable( init_tsr, name = "init_weight_var" )
        
        return weight_var


    def init_bias_variable( self, input_shape ):
        """
        バイアス項 b の初期化を行う。
        バイアス項は TensorFlow の Variable で定義することで、
        学習過程（最適化アルゴリズム Optimizer の session.run(...)）で自動的に TensorFlow により、変更される値となる。

        [Input]
            input_shape : [int,int]
                バイアス項の Variable を初期化するための Tensor の形状

        [Output]
            ゼロ初期化された重みの Variable 
            session.run(...) はされていない状態。
        """

        #init_tsr = tf.zeros( shape = input_shape )
        init_tsr = tf.random_normal( shape = input_shape )

        # バイアス項の Variable
        bias_var = tf.Variable( init_tsr, name = "init_bias_var" )

        return bias_var


    def model( self ):
        """
        モデルの定義（計算グラフの構築）を行い、
        最終的なモデルの出力のオペレーターを設定する。

        [Output]
            self._y_out_op : Operator
                モデルの出力のオペレーター
        """
        #--------------------------------------------------------------
        # 埋め込み行列（単語ベクトルの集合）と埋め込み探索演算を作成
        #--------------------------------------------------------------
        # with tf.name_scope( "embedding_layer" ):

        # 埋め込み行列を表す Variable
        self._embedding_matrix_var = tf.Variable( 
                                         tf.random_uniform( [self._n_vocab, self._n_in_sequence_encoder], -1.0, 1.0 ),
                                         name = "embedding_matrix_var"
                                     )

        # tf.nn.embedding_lookup(...) : バッチ内の各ソース単語について、ベクトルをルックアップ（検索）
        # self._embedding_lookup_op / shape = [None, self._n_in_sequence_encoder, self._n_in_sequence_encoder]
        self._embedding_lookup_op = tf.nn.embedding_lookup( self._embedding_matrix_var, self._X_holder )
        #embedding_expanded_op = tf.expand_dims( self._embedding_lookup_op, -1 )
        print( "self._embedding_lookup_op :", self._embedding_lookup_op )

        # 埋め込みを 1 次元 Tensor 状に reshape
        # tf.split(...) : Tensorを指定した次元方向に分割
        # shape = [None, self._n_in_sequence_encoder, self._n_in_sequence_encoder] → shape = [self._n_in_sequence_encoder]
        # 各 Tensor の shape は、rnn_inputs[i] / shape = [None, 1, self._n_in_sequence_encoder] 
        rnn_inputs = tf.split( 
                         value = self._embedding_lookup_op,                 # 分割する Tensor
                         num_or_size_splits = self._n_in_sequence_encoder,  # 分割する数
                         axis=1                                             # 分割する次元方向
                     )
        print( "rnn_inputs :", rnn_inputs )
        
        # shape = 1 の次元を trimmed（トリミング）
        # tf.squeeze(...) : 指定された size 数に該当する次元を削除する。
        # shape = [None, 1, self._n_in_sequence_encoder] → shape = [None, self._n_in_sequence_encoder]
        # 各 Tensor の shape は、rnn_inputs_trimmed[i] / shape = [None, self._n_in_sequence_encoder] 
        rnn_inputs_trimmed = [ tf.squeeze( tsr, [1] ) for tsr in rnn_inputs ]
        print( "rnn_inputs_trimmed :", rnn_inputs_trimmed )

        #--------------------------------------------------------------
        # Encoder
        # Encoder は不要？
        #--------------------------------------------------------------
        # 忘却ゲートなしの LSTM
        cell_encoder = tf.contrib.rnn.BasicLSTMCell( self._n_hiddenLayer )
        init_state_encoder = cell_encoder.zero_state( self._batch_size_holder, tf.float32 )
        self._rnn_cells_encoder.append( cell_encoder )
        self._rnn_states_encoder.append( init_state_encoder )
        
        #--------------------------------------------------------------
        # Decoder
        #--------------------------------------------------------------
        # 隠れ層 → 出力層への重み
        self._weights.append( self.init_weight_variable( input_shape = [self._n_hiddenLayer, self._n_vocab] ) )
        self._biases.append( self.init_bias_variable( input_shape = [self._n_vocab] ) )

        # ? 損失関数等の評価指数の計算時の RNN の再帰処理（ループ処理）を行う関数
        # i 番目の出力から、i+1 番目の入力（埋め込みベクトル）を取得する。
        # 後の、tf.contrib.legacy_seq2seq.rnn_decoder の call 関数の引数 loop_function で指定
        def eval_rnn_loop( prev_output_op, count ):
            # prev_output_op : i 番目の出力
            # matmul 計算時、直前の出力 self._rnn_cells_decoder[-1] を入力に用いる
            prev_trans_output_op = tf.matmul( prev_output_op, self._weights[-1] ) + self._biases[-1]

            # ? 出力インデックスを取得
            # tf.stop_gradient(...) : https://stackoverflow.com/questions/33727935/how-to-use-stop-gradient-in-tensorflow
            #   an operation that acts as the identity function in the forward direction,
            #   but stops the accumulated gradient from flowing through that operator in the backward direction. 
            #    It does not prevent backpropagation altogether, but instead prevents an individual tensor from contributing to the gradients that are computed for an expression. 
            prev_op_symbol = tf.stop_gradient( tf.arg_max( prev_trans_output_op, 1 ) )

            # 埋め込みベクトルを取得
            output = tf.nn.embedding_lookup( self._embedding_matrix_var, prev_op_symbol )
            
            return output

        # ? Decoder からの再帰処理に基づく、出力リストと最終的な state を取得する。
        # tf.contrib.legacy_seq2seq.rnn_decoder : RNN decoder for the sequence-to-sequence model.
        # [Args:]
        #   decoder_inputs : A list of 2D Tensors [batch_size x input_size].
        #   initial_state: 2D Tensor with shape [batch_size x cell.state_size].
        #   cell: rnn_cell.RNNCell defining the cell function and size.
        #   loop_function:
        #       If not None, this function will be applied to the i-th output in order to generate the i+1-st input, 
        #       and decoder_inputs will be ignored, except for the first element ("GO" symbol). 
        #       This can be used for decoding, but also for training to emulate http://arxiv.org/abs/1506.03099. Signature -- loop_function(prev, i) = next
        #
        #  f.contrib.legacy_seq2seq.rnn_decoder : <function rnn_decoder at 0x00000206908E0158>
        decoder = tf.contrib.legacy_seq2seq.rnn_decoder
        print( "tf.contrib.legacy_seq2seq.rnn_decoder :", decoder ) 
        
        """
        # トレーニング処理中の場合のルート
        if ( self._bTraining_holder == True ):
            # tf.contrib.legacy_seq2seq.rnn_decoder の __call__() 関数を呼び出し、
            # Decoder からの再帰処理に基づく、出力リストと最終的な state を取得する。
            # shape = [self._n_in_sequence_decoder] 個の Tensor 配列 / 各 Tensor の shape = [None, self._n_hidden_Layer]
            outputs_decoder, last_state_decoder = decoder(
                                                      decoder_inputs = rnn_inputs_trimmed,  # 埋め込み層からの入力
                                                      initial_state = self._rnn_states_encoder[-1],
                                                      cell = self._rnn_cells_encoder[-1],
                                                      loop_function = None
                                                  )

        # loss 値などの評価用の値の計算時のルート
        else:
            # tf.contrib.legacy_seq2seq.rnn_decoder の __call__() 関数を呼び出し、
            # Decoder からの再帰処理に基づく、出力リストと最終的な state を取得する。
            outputs_decoder, last_state_decoder = decoder(
                                                      decoder_inputs = rnn_inputs_trimmed,  # 埋め込み層からの入力
                                                      initial_state = self._rnn_states_encoder[-1],
                                                      cell = self._rnn_cells_encoder[-1],
                                                      loop_function = eval_rnn_loop
                                                  )

        """

        # tf.contrib.legacy_seq2seq.rnn_decoder の __call__() 関数を呼び出し、
        # Decoder からの再帰処理に基づく、出力リストと最終的な state を取得する。
        # shape = [self._n_in_sequence_decoder] 個の Tensor 配列 / 各 Tensor の shape = [None, self._n_hidden_Layer]
        outputs_decoder, last_state_decoder = decoder(
                                                  decoder_inputs = rnn_inputs_trimmed,  # 埋め込み層からの入力
                                                  initial_state = self._rnn_states_encoder[-1],
                                                  cell = self._rnn_cells_encoder[-1],
                                                  loop_function = None
                                              )

        print( "outputs_decoder :\n", outputs_decoder )
        
        # Decoder の出力を `tf.concat(...)` で結合し、`tf.reshape(...)` で適切な形状に reshape する。 
        # self.outputs_decoder の形状を shape = ( データ数, 隠れ層のノード数 ) に reshape 
        # tf.concat(...) : Tensorを結合する。引数 axis で結合する dimension を決定
        output = tf.reshape( 
                     tf.concat( outputs_decoder, axis = 1 ),
                     shape = [ -1, self._n_hiddenLayer ]
                 )
        
        print( "output :\n", output )

        #--------------------------------------------------------------
        # 出力層
        #--------------------------------------------------------------
        # 出力層への入力
        # shape = [None, self._n_vocab]
        y_in_op = tf.matmul( output, self._weights[-1] ) + self._biases[-1]
        
        # 最終的な出力
        # shape = [None, self._n_vocab]
        self._y_out_op = tf.nn.softmax( y_in_op )

        return self._y_out_op


    def loss( self ):

        # ?
        # tf.contrib.legacy_seq2seq.sequence_loss_by_example : Weighted cross-entropy loss for a sequence of logits (per example).
        loss_func = tf.contrib.legacy_seq2seq.sequence_loss_by_example

        return self._loss_op



    def optimizer( self, nnOptimizer ):
        """
        モデルの最適化アルゴリズムの設定を行う。

        [Input]
            nnOptimizer : NNOptimizer のクラスのオブジェクト

        [Output]
            optimizer の train_step
        """
        self._optimizer = nnOptimizer._optimizer
        self._train_step = nnOptimizer.train_step( self._loss_op )
        
        return self._train_step


    def fit( self, X_train, y_train ):
        """
        指定されたトレーニングデータで、モデルの fitting 処理を行う。

        [Input]
            X_train : numpy.ndarray ( shape = [n_samples, n_features] )
                トレーニングデータ（特徴行列）
            
            y_train : numpy.ndarray ( shape = [n_samples] )
                トレーニングデータ用のクラスラベル（教師データ）のリスト

        [Output]
            self : 自身のオブジェクト
        """
        #----------------------------
        # 学習開始処理
        #----------------------------
        # Variable の初期化オペレーター
        self._init_var_op = tf.global_variables_initializer()

        # Session の run（初期化オペレーター）
        self._session.run( self._init_var_op )

        #-------------------
        # 学習処理
        #-------------------
        # for ループでエポック数分トレーニング
        for epoch in range( self._epochs ):
            # ミニバッチ学習処理のためランダムサンプリング
            idx_shuffled = numpy.random.choice( len(X_train), size = self._batch_size )
            X_train_shuffled = X_train[ idx_shuffled ]
            y_train_shuffled = y_train[ idx_shuffled ]
            
            # 設定された最適化アルゴリズム Optimizer でトレーニング処理を run
            self._session.run(
                self._train_step,
                feed_dict = {
                    self._X_holder: X_train_shuffled,
                    self._t_holder: y_train_shuffled,
                    self._batch_size_holder: self._batch_size,
                    self._bTraining_holder: True
                }
            )
            
            # 評価処理を行う loop か否か
            # % : 割り算の余りが 0 で判断
            if ( ( (epoch+1) % self._eval_step ) == 0 ):
                # 損失関数値の算出
                loss = self._loss_op.eval(
                       session = self._session,
                       feed_dict = {
                           self._X_holder: X_train_shuffled,
                           self._t_holder: y_train_shuffled,
                           self._batch_size_holder: self._batch_size,
                           self._bTraining_holder: False
                       }
                   )

                self._losses_train.append( loss )
                print( "epoch %d / loss = %f" % ( epoch, loss ) )

        return self._y_out_op


    def predict( self, X_test ):
        """
        fitting 処理したモデルで、推定を行い、
        Encoder に入力するシーケンスデータに対する Decoder の予想値（応答値）を 
        one-hot encode 処理前のインデックス値で返す。

        [Input]
            X_test : numpy.ndarry / shape = [n_samples, n_in_sequence_encoder, one-hot vector size]
                予想したいシーケンスデータ
                n_samples : シーケンスデータのサンプル数
                n_in_sequence_encoder : Encoder に入力するシーケンスのサイズ
                one-hot vector size : 各単語の one-hot encoding 後のサイズ

        [Output]
            predicts : numpy.ndarry ( shape = [n_samples, n_in_sequence_encoder] )
                予想結果（分類モデルの場合は、クラスラベル）
        """
        prob = self._session.run(
                   self._y_out_op,
                   feed_dict = { 
                       self._X_holder: X_test,
                       self._batch_size_holder: len( X_test[:,0,0] ),
                       self._bTraining_holder: False
                   }
               )
        #print( "prob :", prob )

        # one-hot encoding 要素方向で argmax して、文字の数値インデックス取得
        # numpy.argmax(...) : 多次元配列の中の最大値の要素を持つインデックスを返す
        # axis : 最大値を読み取る軸の方向 (-1 : 最後の次元数、この場合 i,j,k の k)
        predicts = numpy.argmax( prob, axis = -1 )

        return predicts


    def predict_proba( self, X_test ):
        """
        fitting 処理したモデルで、推定を行い、
        Encoder に入力するシーケンスデータに対する Decoder のクラスの所属確率の予想値を返す。
        
        [Input]
            X_test : numpy.ndarry / shape = [n_samples, n_in_sequence_encoder, one-hot vector size]
                予想したいシーケンスデータ
                n_samples : シーケンスデータのサンプル数
                n_in_sequence_encoder : Encoder に入力するシーケンスのサイズ
                one-hot vector size : 各単語の one-hot encoding 後のサイズ

        [Output]
            prob : nadarry 
                所属確率の予想値のリスト
        """
        prob = self._y_out_op.eval(
                   session = self._session,
                   feed_dict = {
                       self._X_holder: X_test,
                       self._batch_size_holder: len( X_test[:,0,0] ),
                       self._bTraining_holder: False
                   }
               )
        
        return prob


    def accuracy( self, X_test, y_test ):
        """
        Encoder に入力する指定したデータでの正解率 [accuracy] を計算する。

        [Input]
            X_test : numpy.ndarry / shape = [n_samples, n_in_sequence_encoder, one-hot vector size]
                予想したいシーケンスデータ
                n_samples : シーケンスデータのサンプル数
                n_in_sequence_encoder : Encoder に入力するシーケンスのサイズ
                one-hot vector size : 各単語の one-hot encoding 後のサイズ
            y_test : numpy.ndarry / shape = [n_samples, n_in_sequence_decoder, one-hot vector size]
                X_test に対する正解データ（教師データ）
                n_samples : シーケンスデータのサンプル数
                n_in_sequence_decoder : Decoder に入力するシーケンスのサイズ
                one-hot vector size : 各単語の one-hot encoding 後のサイズ

        [Output]
            accuracy : float
                正解率 (0.0~1.0)
        """
        # 予想ラベルを算出する。
        predicts = self.predict( X_test )

        # y_test の one-hot encode された箇所を argmax し、文字に対応した数値インデックスに変換
        y_labels = numpy.argmax( y_test, axis = -1 )
        #print( "y_labels :", y_labels )

        # 正解数
        n_corrects = 0
        resluts = numpy.equal( predicts, y_labels )     # shape = (n_sample, n_in_sequence_decoder )
        
        for i in range( len(X_test[:,0,0]) ):
            # 各サンプルのシーケンス内で全てで True : [True, True, True, True] なら 正解数を +1 カウント
            if ( all( resluts[i] ) == True ):
                n_corrects = n_corrects + 1

        print( "n_corrects : {}".format (n_corrects) )
 
        # 正解率
        accuracy = n_corrects / len( X_test[:,0,0] )

        return accuracy