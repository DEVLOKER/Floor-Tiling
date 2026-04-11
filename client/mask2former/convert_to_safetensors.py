import os
from pathlib import Path
from transformers import Mask2FormerForUniversalSegmentation

def convert_to_safetensors():
    """Converts pytorch_model.bin to model.safetensors for Mask2Former."""
    models_dir = Path(__file__).resolve().parent / "models"
    
    bin_path = models_dir / "pytorch_model.bin"
    safetensors_path = models_dir / "model.safetensors"
    
    print(f"🔍 Checking directory: {models_dir}")
    
    if not bin_path.exists():
        print(f"❌ Error: {bin_path.name} not found in {models_dir}")
        print("Please download it from the link in download.txt first.")
        return

    print(f"🟡 Loading model from {bin_path.name}...")
    try:
        # Load using the directory (it will pick up config.json and pytorch_model.bin)
        model = Mask2FormerForUniversalSegmentation.from_pretrained(str(models_dir))
        
        print(f"✅ Model loaded. Converting to safetensors...")
        
        # Save back to the same directory (transformers 4.27+ defaults to safetensors)
        model.save_pretrained(str(models_dir), safe_serialization=True)
        
        if safetensors_path.exists():
            print(f"✨ Success! {safetensors_path.name} has been created.")
            print(f"💡 You can now safely delete {bin_path.name} if you want to save space.")
        else:
            print("❓ Conversion finished but model.safetensors was not found.")
            
    except Exception as e:
        print(f"❌ An error occurred during conversion: {e}")

if __name__ == "__main__":
    convert_to_safetensors()
