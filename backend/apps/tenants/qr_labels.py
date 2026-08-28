import io

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


LABEL_WIDTH = 70 * mm
LABEL_HEIGHT = 40 * mm
MARGIN = 10 * mm
QR_SIZE = 30 * mm


def _make_qr_image(map_id):
    qr_data = f'metrix://room/{map_id}'
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return ImageReader(buffer)


def generate_single_label_pdf(room):
    """Одна наклейка на странице (для печати на отдельных стикерах)."""
    buffer = io.BytesIO()
    page_width = LABEL_WIDTH + 2 * MARGIN
    page_height = LABEL_HEIGHT + 2 * MARGIN
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    qr_image = _make_qr_image(room.map_id)
    qr_x = MARGIN
    qr_y = MARGIN + (LABEL_HEIGHT - QR_SIZE) / 2
    c.drawImage(qr_image, qr_x, qr_y, width=QR_SIZE, height=QR_SIZE)

    text_x = qr_x + QR_SIZE + 5 * mm
    text_y = MARGIN + LABEL_HEIGHT - 12 * mm
    c.setFont('Helvetica-Bold', 14)
    c.drawString(text_x, text_y, f'Помещение {room.number}')
    c.setFont('Helvetica', 9)
    c.drawString(text_x, text_y - 6 * mm, f'Этаж {room.floor}')
    c.drawString(text_x, text_y - 12 * mm, room.map_id)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def generate_batch_labels_pdf(rooms):
    """Лист А4 с сеткой наклеек (для пакетной печати нескольких помещений)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    cols = int((page_width - 2 * MARGIN) // LABEL_WIDTH)
    rows = int((page_height - 2 * MARGIN) // LABEL_HEIGHT)
    per_page = cols * rows

    for index, room in enumerate(rooms):
        pos_on_page = index % per_page
        if index > 0 and pos_on_page == 0:
            c.showPage()

        col = pos_on_page % cols
        row = pos_on_page // cols

        label_x = MARGIN + col * LABEL_WIDTH
        label_y = page_height - MARGIN - (row + 1) * LABEL_HEIGHT

        qr_image = _make_qr_image(room.map_id)
        qr_x = label_x + 3 * mm
        qr_y = label_y + (LABEL_HEIGHT - QR_SIZE) / 2
        c.drawImage(qr_image, qr_x, qr_y, width=QR_SIZE, height=QR_SIZE)

        text_x = qr_x + QR_SIZE + 3 * mm
        text_y = label_y + LABEL_HEIGHT - 10 * mm
        c.setFont('Helvetica-Bold', 11)
        c.drawString(text_x, text_y, f'Пом. {room.number}')
        c.setFont('Helvetica', 7)
        c.drawString(text_x, text_y - 5 * mm, f'Этаж {room.floor}')
        c.drawString(text_x, text_y - 10 * mm, room.map_id)

        c.rect(label_x, label_y, LABEL_WIDTH, LABEL_HEIGHT)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer