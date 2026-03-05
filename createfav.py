from PIL import Image

def convert_jpg_to_favicon(input_path, output_path="favicon.ico"):
    with Image.open(input_path) as img:
        # 1. Handle non-square images by cropping to center
        width, height = img.size
        min_dim = min(width, height)
        left = (width - min_dim) / 2
        top = (height - min_dim) / 2
        right = (width + min_dim) / 2
        bottom = (height + min_dim) / 2
        
        img_square = img.crop((left, top, right, bottom))

        # 2. Save with multiple sizes inside the .ico
        # Standard sizes: 16x16 (tabs), 32x32 (high-res), 48x48 (taskbar)
        icon_sizes = [(16, 16), (32, 32), (48, 48)]
        img_square.save(output_path, format="ICO", sizes=icon_sizes)
        print(f"Success! {output_path} created with multiple resolutions.")

if __name__ == "__main__":
    # Replace 'your_image.jpg' with your actual filename
    convert_jpg_to_favicon("missile.jpg")