"""模型注册表 + ComfyUI 工作流构造器"""
import os

# Z-Image-Turbo diffusers 目录（AutoDL 数据盘）
ZIMAGE_PATH = "z-image-turbo"  # 相对 ComfyUI/models/diffusers


def build_qwen_image(prompt, negative, width, height, steps, cfg, seed, batch, sampler="euler", scheduler="karras"):
    """Qwen-Image GGUF（Q3_K_M 量化）：UnetLoaderGGUF + CLIPLoaderGGUF(qwen_image)"""
    return {
        "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "Qwen_Image-Q3_K_M.gguf"}},
        "11": {"class_type": "CLIPLoaderGGUF", "inputs": {
            "clip_name": "qwen2.5_vl_7b_q4_k_m.gguf", "type": "qwen_image"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "13": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["11", 0]}},
        "14": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["11", 0]}},
        "15": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": batch}},
        "16": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
            "model": ["10", 0], "positive": ["13", 0], "negative": ["14", 0],
            "latent_image": ["15", 0]}},
        "17": {"class_type": "VAEDecode", "inputs": {"samples": ["16", 0], "vae": ["12", 0]}},
        "18": {"class_type": "SaveImage", "inputs": {"filename_prefix": "qwen_image", "images": ["17", 0]}},
    }


def build_sdxl(prompt, negative, width, height, steps, cfg, seed, batch, sampler="euler", scheduler="normal"):
    """SDXL base 1.0（单文件 checkpoint）"""
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": batch}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
            "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "sdxl", "images": ["8", 0]}},
    }


def build_z_image(prompt, negative, width, height, steps, cfg, seed, batch, sampler="dpmpp_2m", scheduler="karras"):
    """Z-Image-Turbo：Kijai fp8 unet + Qwen3-4B text encoder + 自带 VAE"""
    return {
        "20": {"class_type": "UNETLoader", "inputs": {"unet_name": "z-image-turbo_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "21": {"class_type": "CLIPLoaderGGUF", "inputs": {
            "clip_name": "qwen3_4b_iq4_xs.gguf", "type": "qwen_image"}},  # 自动检测 Qwen3-4B → Z-Image
        "22": {"class_type": "VAELoader", "inputs": {"vae_name": "z_image_vae.safetensors"}},
        "23": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["21", 0]}},
        "24": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["21", 0]}},
        "25": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": batch}},
        "26": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
            "model": ["20", 0], "positive": ["23", 0], "negative": ["24", 0], "latent_image": ["25", 0]}},
        "27": {"class_type": "VAEDecode", "inputs": {"samples": ["26", 0], "vae": ["22", 0]}},
        "28": {"class_type": "SaveImage", "inputs": {"filename_prefix": "z_image", "images": ["27", 0]}},
    }


def build_sd15(prompt, negative, width, height, steps, cfg, seed, batch, sampler="euler", scheduler="normal"):
    """SD 1.5（diffusers 目录，标准 StableDiffusionPipeline）"""
    return {
        "30": {"class_type": "DiffusersLoader", "inputs": {"model_path": "sd15"}},
        "31": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["30", 1]}},
        "32": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["30", 1]}},
        "33": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": batch}},
        "34": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
            "model": ["30", 0], "positive": ["31", 0], "negative": ["32", 0], "latent_image": ["33", 0]}},
        "35": {"class_type": "VAEDecode", "inputs": {"samples": ["34", 0], "vae": ["30", 2]}},
        "36": {"class_type": "SaveImage", "inputs": {"filename_prefix": "sd15", "images": ["35", 0]}},
    }


MODELS = {
    "sd15": {
        "name": "Stable Diffusion 1.5 (diffusers)",
        "builder": build_sd15,
        "defaults": {"width": 512, "height": 512, "steps": 25, "cfg": 7.0,
                     "sampler": "euler", "scheduler": "normal"},
        "note": "最老的模型，仅作基准对比",
    },
    "qwen-image": {
        "name": "Qwen-Image (Q3_K_M, GGUF)",
        "builder": build_qwen_image,
        # 官方蒸馏配置（实测 9.5 分，对比见 docs/parameter-guide.md）
        "defaults": {"width": 1280, "height": 1280, "steps": 12, "cfg": 1.0,
                     "sampler": "res_multistep", "scheduler": "simple"},
        "note": "中文理解强；默认=官方蒸馏配置，勿用高步数/高cfg",
    },
    "sdxl": {
        "name": "Stable Diffusion XL base 1.0",
        "builder": build_sdxl,
        "defaults": {"width": 1024, "height": 1024, "steps": 20, "cfg": 7.0,
                     "sampler": "euler", "scheduler": "normal"},
        "note": "英文提示词效果更稳",
    },
    "z-image-turbo": {
        "name": "Z-Image-Turbo (diffusers)",
        "builder": build_z_image,
        "defaults": {"width": 1024, "height": 1024, "steps": 8, "cfg": 1.0,
                     "sampler": "dpmpp_2m", "scheduler": "karras"},
        "note": "Turbo 少步数快速出图；DMD 蒸馏不支持负面提示词，cfg 建议 1.0-3.0",
    },
}
