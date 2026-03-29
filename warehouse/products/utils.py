import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from django.conf import settings
import os
import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def parse_vendor_invoice(file_obj):
    extracted_items = []
    
    try:
        with pdfplumber.open(file_obj) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError("PDF file is empty")
            
            page = pdf.pages[0]
            
            # Try table extraction first
            tables = page.extract_tables()
            
            if tables:
                # Original table parsing logic
                table = tables[0]
                if not table or len(table) < 2:
                    raise ValueError("Table has no data rows")
                
                headers = table[0]
                column_mapping = identify_columns(headers)
                
                if not column_mapping:
                    raise ValueError("Could not identify required columns")
                
                for row_idx, row in enumerate(table[1:], start=2):
                    try:
                        if not row or all(cell is None or str(cell).strip() == '' for cell in row):
                            continue
                        
                        sku = extract_cell_value(row, column_mapping.get('sku'))
                        qty = extract_cell_value(row, column_mapping.get('qty'))
                        price = extract_cell_value(row, column_mapping.get('price'))
                        
                        if not sku or qty is None or price is None:
                            continue
                        
                        extracted_items.append({
                            "sku": str(sku).strip(),
                            "quantity": int(qty),
                            "price": float(str(price).replace('$', '').replace(',', '').strip())
                        })
                    except (ValueError, IndexError, TypeError) as e:
                        logger.warning(f"Row {row_idx}: Failed to parse - {str(e)}")
                        continue

            else:
                # Fallback: parse raw text line by line
                logger.info("No tables found, attempting text-based parsing")
                extracted_items = parse_invoice_from_text(page)
            
            if not extracted_items:
                raise ValueError("No valid items extracted from invoice")
                
    except Exception as e:
        logger.error(f"PDF parsing failed: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to parse invoice: {str(e)}")
    
    return extracted_items

def parse_invoice_from_text(page):
    """
    Fallback parser for text-based PDFs without table borders.
    Uses X position ranges from header to bucket data cells.
    """
    extracted_items = []

    words = page.extract_words()
    if not words:
        raise ValueError("No text content found in PDF")

    # Group words into rows by Y position (3px tolerance)
    rows = {}
    for word in words:
        y = round(word['top'] / 3) * 3
        if y not in rows:
            rows[y] = []
        rows[y].append(word)

    # Sort rows top to bottom
    sorted_y = sorted(rows.keys())
    sorted_rows = []
    for y in sorted_y:
        row_words = sorted(rows[y], key=lambda w: w['x0'])
        sorted_rows.append(row_words)  # keep full word objects (with x0, text)

    # Find header row by looking for SKU/Qty/Price keywords
    header_row = None
    header_idx = 0
    for i, row in enumerate(sorted_rows):
        row_text = ' '.join(w['text'] for w in row).lower()
        if 'sku' in row_text and ('qty' in row_text or 'price' in row_text):
            header_row = row
            header_idx = i
            break

    if not header_row:
        raise ValueError("Could not find header row in PDF text")

    logger.info(f"Header words: {[w['text'] for w in header_row]}")

    # Build column X ranges from header word positions
    # Each header word defines a column — capture its x0 as the column start
    col_map = {}
    for word in header_row:
        text = word['text'].lower().strip()
        x0 = word['x0']

        if text == 'sku':
            col_map['sku'] = x0
        elif text == 'qty' or text == 'quantity':
            col_map['qty'] = x0
        elif text == 'price' or text == 'rate' or text == 'cost':
            col_map['price'] = x0
        # 'Product', 'Name' etc. are intentionally skipped

    logger.info(f"Column X positions: {col_map}")

    if not all(k in col_map for k in ['sku', 'qty', 'price']):
        raise ValueError(f"Could not identify all required columns. Found: {list(col_map.keys())}")

    # Sort column x positions to define boundaries
    all_x = sorted(col_map.values())

    def get_col_name(x0):
        """Find which column a word belongs to based on its X position"""
        assigned = None
        for col, col_x in col_map.items():
            if x0 >= col_x - 5:  # 5px left tolerance
                assigned = col
        return assigned

    # Parse data rows after header
    for row_idx, row in enumerate(sorted_rows[header_idx + 1:], start=header_idx + 2):
        try:
            if not row:
                continue

            # Skip rows that are clearly not data (e.g. blank or single word)
            if len(row) < 2:
                continue

            # Bucket each word into a column by X position
            buckets = {'sku': [], 'qty': [], 'price': []}
            for word in row:
                col = get_col_name(word['x0'])
                if col in buckets:
                    buckets[col].append(word['text'])

            sku = ' '.join(buckets['sku']).strip()
            qty = ' '.join(buckets['qty']).strip()
            price = ' '.join(buckets['price']).strip()

            logger.info(f"Row {row_idx} → SKU: {sku}, Qty: {qty}, Price: {price}")

            if not sku or not qty or not price:
                continue

            qty_clean = int(qty)
            price_clean = float(price.replace('$', '').replace(',', '').strip())

            if qty_clean <= 0 or price_clean <= 0:
                continue

            extracted_items.append({
                "sku": sku,
                "quantity": qty_clean,
                "price": price_clean
            })

        except (ValueError, IndexError, TypeError) as e:
            logger.warning(f"Row {row_idx}: Failed to parse - {str(e)}")
            continue

    return extracted_items




def identify_columns(headers):
    """Identify which column contains SKU, Qty, and Price"""
    mapping = {}
    
    for idx, header in enumerate(headers):
        if not header:
            continue
        
        header_lower = str(header).lower().strip()
        
        # Identify SKU column
        if any(keyword in header_lower for keyword in ['sku', 'code', 'part', 'item']):
            mapping['sku'] = idx
        
        # Identify Quantity column
        elif any(keyword in header_lower for keyword in ['qty', 'quantity', 'units', 'count']):
            mapping['qty'] = idx
        
        # Identify Price column
        elif any(keyword in header_lower for keyword in ['price', 'rate', 'cost', 'amount']):
            mapping['price'] = idx
    
    # Verify we found all required columns
    required = ['sku', 'qty', 'price']
    if all(col in mapping for col in required):
        return mapping
    
    # Try common patterns if identification failed
    if len(headers) >= 4:
        # Assume standard order: SKU, Name, Qty, Price
        mapping = {
            'sku': 0,
            'qty': 2,
            'price': 3
        }
        return mapping
    
    return None


def extract_cell_value(row, column_index):
    """Extract and clean cell value"""
    if column_index is None or column_index >= len(row):
        return None
    
    value = row[column_index]
    if value is None:
        return None
    
    return str(value).strip()


def generate_supplier_invoice_pdf(items, supplier_name, profit_margin):
    """
    Generates a new Invoice PDF with added profit.
    Returns the file path as URL.
    """
    # Sanitize inputs
    supplier_name = sanitize_filename(supplier_name)
    profit_margin = float(profit_margin)
    
    # Generate unique filename
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"invoice_{unique_id}_{timestamp}.pdf"
    
    # Create secure file path
    invoices_dir = os.path.join(settings.MEDIA_ROOT, 'invoices')
    file_path = os.path.join(invoices_dir, filename)
    
    # Ensure directory exists with secure permissions
    os.makedirs(invoices_dir, exist_ok=True)
    
    try:
        # Create PDF
        c = canvas.Canvas(file_path, pagesize=A4)
        width, height = A4
        
        # Header
        y_position = draw_invoice_header(c, width, height, supplier_name)
        
        # Table Header
        y_position = draw_table_header(c, y_position)
        
        # Line Items
        grand_total, y_position = draw_line_items(c, items, y_position, height)
        
        # Footer
        draw_invoice_footer(c, y_position, grand_total)
        
        c.save()
        
        # Return URL
        return f"{settings.MEDIA_URL}invoices/{filename}"
        
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to generate invoice: {str(e)}")


def sanitize_filename(name):
    """Remove unsafe characters from filename"""
    if not name:
        return "Customer"
    
    # Remove any path traversal attempts
    name = name.replace('/', '').replace('\\', '').replace('..', '')
    
    # Keep only alphanumeric and spaces
    safe_name = ''.join(c for c in name if c.isalnum() or c.isspace())
    
    # Limit length and replace spaces
    safe_name = safe_name[:50].strip().replace(' ', '_')
    
    return safe_name if safe_name else "Customer"


def draw_invoice_header(c, width, height, supplier_name):
    """Draw invoice header"""
    # Company Logo/Title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "WAREHOUSE MANAGEMENT SYSTEM")
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 85, "TAX INVOICE")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 110, f"Bill To: {supplier_name}")
    c.drawString(50, height - 125, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    c.drawString(50, height - 140, f"Invoice #: INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}")
    
    return height - 160


def draw_table_header(c, y_position):
    """Draw table headers"""
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y_position, "Product Name")
    c.drawString(300, y_position, "Qty")
    c.drawString(380, y_position, "Unit Price")
    c.drawString(500, y_position, "Total")
    c.line(50, y_position - 5, 550, y_position - 5)
    
    return y_position - 25


def draw_line_items(c, items, y_position, height):
    """Draw invoice line items"""
    c.setFont("Helvetica", 10)
    grand_total = 0
    
    for item in items:
        # Check page break
        if y_position < 80:
            c.showPage()
            y_position = height - 50
            c.setFont("Helvetica", 10)
        
        # Truncate long product names
        product_name = item['product_name'][:35]
        if len(item['product_name']) > 35:
            product_name += "..."
        
        # Draw item
        c.drawString(50, y_position, product_name)
        c.drawString(300, y_position, str(item['quantity']))
        c.drawString(380, y_position, f"${item['new_price']:.2f}")
        c.drawString(500, y_position, f"${item['total']:.2f}")
        
        grand_total += item['total']
        y_position -= 20
    
    return grand_total, y_position


def draw_invoice_footer(c, y_position, grand_total):
    """Draw invoice footer with totals"""
    c.line(50, y_position, 550, y_position)
    
    # Calculate tax (assuming 10% GST)
    tax = grand_total * 0.10
    total_with_tax = grand_total + tax
    
    c.setFont("Helvetica", 10)
    c.drawString(400, y_position - 15, f"Subtotal: ${grand_total:.2f}")
    c.drawString(400, y_position - 30, f"GST (10%): ${tax:.2f}")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, y_position - 50, f"Grand Total: ${total_with_tax:.2f}")
    
    # Add payment terms
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, "Payment Terms: Net 30 days")
    c.drawString(50, 35, "Thank you for your business!")