from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("../data/sample/resume.pdf", pagesize=letter)
w, h = letter
y = h - 72

lines = [
    ("Maya Chen", "Helvetica-Bold", 16),
    ("maya.chen@example.com  |  +1 (415) 555 0182  |  San Francisco, CA", "Helvetica", 10),
    ("linkedin.com/in/mayachen  |  github.com/mayachen", "Helvetica", 10),
    ("", "Helvetica", 10),
    ("Summary:", "Helvetica-Bold", 12),
    ("Senior backend engineer with 8 years building distributed systems.", "Helvetica", 10),
    ("", "Helvetica", 10),
    ("Skills:", "Helvetica-Bold", 12),
    ("Python, JS, React, PostgreSQL, k8s, Docker, REST", "Helvetica", 10),
    ("", "Helvetica", 10),
    ("Experience:", "Helvetica-Bold", 12),
    ("Senior Software Engineer, Acme Robotics (Jan 2021 - Present)", "Helvetica", 10),
    ("Backend Engineer, Globex (Jun 2018 - Dec 2020)", "Helvetica", 10),
    ("", "Helvetica", 10),
    ("Education:", "Helvetica-Bold", 12),
    ("B.S. Computer Science, UC Berkeley, 2016", "Helvetica", 10),
]

for text, font, size in lines:
    c.setFont(font, size)
    c.drawString(72, y, text)
    y -= size + 8

c.save()
print("wrote data/sample/resume.pdf")
