import asyncio
import logging
import os
import subprocess
import time
import uuid
from abc import ABC, ABCMeta, abstractmethod
from datetime import datetime
from gtts import gTTS
import edge_tts
import ChatTTS
import torch
import torchaudio
import soundfile as sf
from kokoro import KModel, KPipeline

logger = logging.getLogger(__name__)


class AbstractTTS(ABC):
    __metaclass__ = ABCMeta

    @abstractmethod
    def to_tts(self, text):
        pass


class GTTS(AbstractTTS):
    def __init__(self, config):
        self.output_file = config.get("output_file")
        self.lang = config.get("lang")

    def _generate_filename(self, extension=".aiff"):
        return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}")

    def _log_execution_time(self, start_time):
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"执行时间: {execution_time:.2f} 秒")

    def to_tts(self, text):
        tmpfile = self._generate_filename(".aiff")
        try:
            start_time = time.time()
            tts = gTTS(text=text, lang=self.lang)
            tts.save(tmpfile)
            self._log_execution_time(start_time)
            return tmpfile
        except Exception as e:
            logger.debug(f"生成TTS文件失败: {e}")
            return None


class MacTTS(AbstractTTS):
    """
    macOS 系统自带的TTS
    voice: say -v ? 可以打印所有语音
    """

    def __init__(self, config):
        super().__init__()
        self.voice = config.get("voice")
        self.output_file = config.get("output_file")

    def _generate_filename(self, extension=".aiff"):
        return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}")

    def _log_execution_time(self, start_time):
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"执行时间: {execution_time:.2f} 秒")

    def to_tts(self, phrase):
        logger.debug(f"正在转换的tts：{phrase}")
        tmpfile = self._generate_filename(".aiff")
        try:
            start_time = time.time()
            res = subprocess.run(
                ["say", "-v", self.voice, "-o", tmpfile, phrase],
                shell=False,
                universal_newlines=True,
            )
            self._log_execution_time(start_time)
            if res.returncode == 0:
                return tmpfile
            else:
                logger.info("TTS 生成失败")
                return None
        except Exception as e:
            logger.info(f"执行TTS失败: {e}")
            return None


class EdgeTTS(AbstractTTS):
    def __init__(self, config):
        self.output_file = config.get("output_file", "tmp/")
        self.voice = config.get("voice")

    def _generate_filename(self, extension=".wav"):
        return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}")

    def _log_execution_time(self, start_time):
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"Execution Time: {execution_time:.2f} seconds")

    async def text_to_speak(self, text, output_file):
        communicate = edge_tts.Communicate(text, voice=self.voice)  # Use your preferred voice
        await communicate.save(output_file)

    def to_tts(self, text):
        tmpfile = self._generate_filename(".wav")
        start_time = time.time()
        try:
            asyncio.run(self.text_to_speak(text, tmpfile))
            self._log_execution_time(start_time)
            return tmpfile
        except Exception as e:
            logger.info(f"Failed to generate TTS file: {e}")
            return None


class CHATTTS(AbstractTTS):
    def __init__(self, config):
        self.output_file = config.get("output_file", ".")
        self.chat = ChatTTS.Chat()
        self.chat.load(compile=False)  # Set to True for better performance
        self.rand_spk = self.chat.sample_random_speaker()

    def _generate_filename(self, extension=".wav"):
        return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}")

    def _log_execution_time(self, start_time):
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"Execution Time: {execution_time:.2f} seconds")

    def to_tts(self, text):
        tmpfile = self._generate_filename(".wav")
        start_time = time.time()
        try:
            params_infer_code = ChatTTS.Chat.InferCodeParams(
                spk_emb=self.rand_spk,  # add sampled speaker
                temperature=.3,  # using custom temperature
                top_P=0.7,  # top P decode
                top_K=20,  # top K decode
            )
            params_refine_text = ChatTTS.Chat.RefineTextParams(
                prompt='[oral_2][laugh_0][break_6]',
            )
            wavs = self.chat.infer(
                [text],
                params_refine_text=params_refine_text,
                params_infer_code=params_infer_code,
            )
            try:
                torchaudio.save(tmpfile, torch.from_numpy(wavs[0]).unsqueeze(0), 24000)
            except:
                torchaudio.save(tmpfile, torch.from_numpy(wavs[0]), 24000)
            self._log_execution_time(start_time)
            return tmpfile
        except Exception as e:
            logger.error(f"Failed to generate TTS file: {e}")
            return None



# class KOKOROTTS(AbstractTTS):
#     def __init__(self, config):
#         from kokoro import KPipeline
#         self.output_file = config.get("output_file", ".")
#         self.lang = config.get("lang", "z")
#         self.pipeline = KPipeline(lang_code=self.lang)  # <= make sure lang_code matches voice
#         self.voice = config.get("voice", "zm_yunyang")
#
#     def _generate_filename(self, extension=".wav"):
#         return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}")
#
#     def _log_execution_time(self, start_time):
#         end_time = time.time()
#         execution_time = end_time - start_time
#         logger.debug(f"Execution Time: {execution_time:.2f} seconds")
#
#     def to_tts(self, text):
#         tmpfile = self._generate_filename(".wav")
#         start_time = time.time()
#         try:
#             generator = self.pipeline(
#                 text, voice=self.voice,  # <= change voice here
#                 speed=1, split_pattern=r'\n+'
#             )
#             for i, (gs, ps, audio) in enumerate(generator):
#                 logger.debug(f"KOKOROTTS: i: {i}, gs：{gs}, ps：{ps}")  # i => index
#                 sf.write(tmpfile, audio, 24000)  # save each audio file
#             self._log_execution_time(start_time)
#             return tmpfile
#         except Exception as e:
#             logger.error(f"Failed to generate TTS file: {e}")
#             return None


class KOKOROTTS(AbstractTTS):
    def __init__(self, config):
        """
        config keys:
          - repo_id: HuggingFace repo ID or local model path (e.g. 'hexgrad/Kokoro-82M-v1.1-zh' or 'models/ckpts/kokoro-v1.1')
          - lang:      'z' for Chinese, 'a' for multilingual/IPA fallback
          - voice:     e.g. 'zf_001' or 'zm_010'
          - output_dir: directory to write wav files to
          - sample_rate: audio sample rate (default 24000)
          - zero_padding: number of zeros between segments (default 5000)
        """
        self.repo_id      = config.get("repo_id", "hexgrad/Kokoro-82M-v1.1-zh")
        self.output_dir   = config.get("output_dir", ".")
        self.lang         = config.get("lang", "z")
        self.voice        = config.get("voice", "zf_001")
        self.sample_rate  = config.get("sample_rate", 24000)

        # device selection
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Check if repo_id is a local path
        is_local_path = os.path.exists(self.repo_id)
        
        # load model if Chinese TTS
        self.model = None
        if self.lang == "z":
            if is_local_path:
                # Use local model files
                config_path = os.path.join(self.repo_id, 'config.json')
                model_path = os.path.join(self.repo_id, 'kokoro-v1_1-zh.pth')
                if not os.path.exists(model_path):
                    # Try to find any .pth file
                    pth_files = [f for f in os.listdir(self.repo_id) if f.endswith('.pth')]
                    if pth_files:
                        model_path = os.path.join(self.repo_id, pth_files[0])
                    else:
                        raise FileNotFoundError(f"No model file (.pth) found in {self.repo_id}")
                
                logger.info(f"Loading Kokoro model from local path: {model_path}")
                self.model = KModel(config=config_path, model=model_path).to(self.device).eval()
            else:
                # Use HuggingFace repo
                self.model = KModel(repo_id=self.repo_id).to(self.device).eval()

        # set up pipelines
        self._setup_pipelines()

    def _setup_pipelines(self):
        # Check if repo_id is a local path
        is_local_path = os.path.exists(self.repo_id)
        
        # English/IPA fallback pipeline
        self.en_pipeline = KPipeline(
            lang_code="a", repo_id=self.repo_id, model=False
        )

        def en_callable(text):
            if text == "Kokoro":
                return "kˈOkəɹO"
            elif text == "Sol":
                return "sˈOl"
            return next(self.en_pipeline(text)).phonemes

        self.en_callable = en_callable

        # Main TTS pipeline
        self.pipeline = KPipeline(
            lang_code=self.lang,
            repo_id=self.repo_id,
            model=self.model,
            en_callable=self.en_callable
        )
        
        # If using local path, preload the voice from local directory
        if is_local_path and self.lang == "z":
            voices_dir = os.path.join(self.repo_id, 'voices')
            if os.path.exists(voices_dir):
                # Pre-load all voices from local directory
                for voice_file in os.listdir(voices_dir):
                    if voice_file.endswith('.pt'):
                        voice_name = voice_file[:-3]  # Remove .pt extension
                        voice_path = os.path.join(voices_dir, voice_file)
                        try:
                            pack = torch.load(voice_path, weights_only=True, map_location='cpu')
                            self.pipeline.voices[voice_name] = pack
                            logger.debug(f"Pre-loaded voice: {voice_name}")
                        except Exception as e:
                            logger.warning(f"Failed to load voice {voice_name}: {e}")

    def _generate_filename(self, extension=".wav"):
        fname = f"tts-{datetime.now().date()}@{uuid.uuid4().hex}{extension}"
        return os.path.join(self.output_dir, fname)

    def _log_execution_time(self, start_time):
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"Execution Time: {execution_time:.2f} seconds")
    @staticmethod
    def _speed_callable(len_ps: int) -> float:
        """
        piecewise linear function to slow down generation for long inputs
        """
        speed = 0.8
        if len_ps <= 83:
            speed = 1.0
        elif len_ps < 183:
            speed = 1.0 - (len_ps - 83) / 500.0
        return speed * 1.1

    def to_tts(self, text: str) -> str:
        """
        Generate TTS for `text`. Returns path to the combined WAV file.
        """
        output_file = self._generate_filename(".wav")
        start_time = time.time()

        try:
            generator = self.pipeline(
                text.replace("\n", " "),
                voice=self.voice,
                speed=self._speed_callable,
                #split_pattern=r"\n+"
            )
            result = next(generator)
            wav = result.audio
            sf.write(output_file, wav, self.sample_rate)

            self._log_execution_time(start_time)
            return output_file
        except Exception as e:
            logger.error(f"[KOKOROTTS] Failed to generate TTS: {e}")
            return ""


def create_instance(class_name, *args, **kwargs):
    # 获取类对象
    cls = globals().get(class_name)
    if cls:
        # 创建并返回实例
        return cls(*args, **kwargs)
    else:
        raise ValueError(f"Class {class_name} not found")
