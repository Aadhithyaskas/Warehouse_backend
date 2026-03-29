# generate_test_invoice.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import os

def generate_test_invoice():
    filename = "test_vendor_invoice.pdf"
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "VENDOR INVOICE")
    
    # Table Headers
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 100, "SKU")
    c.drawString(150, height - 100, "Product Name")
    c.drawString(300, height - 100, "Qty")
    c.drawString(400, height - 100, "Price")
    
    # Line
    c.line(50, height - 105, 550, height - 105)
    
    # Data
    y = height - 125
    c.setFont("Helvetica", 10)
    
    # Sample Aachi products
    products = [
        ("ACH-SMP-1KG", "Aachi Sambar Powder", "100", "$180.00"),
        ("ACH-CHK-200G", "Aachi Chicken Masala", "50", "$85.00"),
        ("ACH-IDL-5KG", "Aachi Idli Rice", "200", "$250.00"),
    ]
    
    for sku, name, qty, price in products:
        c.drawString(50, y, sku)
        c.drawString(150, y, name)
        c.drawString(300, y, qty)
        c.drawString(400, y, price)
        y -= 25
    
    c.save()
    print(f"✅ Test invoice created: {filename}")

if __name__ == "__main__":
    generate_test_invoice()