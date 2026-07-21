import cv2
import numpy as np

class ClassicalCVEngine:
    def analyze_image_quality(self, image_bytes):
        """
        Calculates mathematical properties of the banknote print.
        Fake notes printed on standard inkjet printers have high ink bleed (lower sharpness)
        and different paper texture compared to RBI Intaglio printing.
        """
        # Load image from bytes
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {"error": "Invalid image data"}

        # Convert to grayscale for mathematical analysis
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Laplacian Variance (Sharpness/Blur Detection)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 2. Canny Edge Density (Intaglio Print Simulation)
        edges = cv2.Canny(gray, 100, 200)
        edge_density = (np.count_nonzero(edges) / edges.size) * 100
        
        # Explicitly cast NumPy types to standard Python types so json.dumps doesn't crash!
        is_blurry = bool(laplacian_var < 150)
        low_edge_density = bool(edge_density < 5.0)

        return {
            "sharpness_score": float(round(laplacian_var, 2)),
            "edge_density": float(round(edge_density, 2)),
            "print_bleed_warning": is_blurry or low_edge_density,
            "cv_signal": "Anomalous" if is_blurry or low_edge_density else "Authentic Pattern"
        }

cv_analyzer = ClassicalCVEngine()