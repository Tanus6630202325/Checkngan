"""หมวดงานกลาง: แมปจากหมวดของแต่ละเว็บ (raw) ก่อน ถ้าไม่เจอค่อยเดาจากชื่อตำแหน่ง
ลำดับในลิสต์มีผล: กฎที่อยู่ก่อนจะถูกเลือกก่อน"""
import re

RULES = [
    ("ไอที / โปรแกรมเมอร์", r"ไอที|คอมพิวเตอร์|information & communication|software|developer|programmer|"
        r"โปรแกรมเมอร์|นักพัฒนา|พัฒนาระบบ|data (scientist|analyst|engineer)|devops|\bit\b|\bqa\b|tester|"
        r"ux|ui/|frontend|backend|full ?stack|network|system admin|ผู้ดูแลระบบ|web ?(design|master)"),
    ("การแพทย์ / สาธารณสุข", r"แพทย์|พยาบาล|เภสัช|สาธารณสุข|healthcare|medical|nurse|nursing|pharmac|dental|ทันต|"
        r"ผู้ช่วยพยาบาล|นักกายภาพ|clinic"),
    ("บัญชี / การเงิน / ธนาคาร", r"บัญชี|การเงิน|account|financ|banking|bank|ธนาคาร|insurance|ประกัน|audit|"
        r"สินเชื่อ|ภาษี|\bcfo\b|treasury"),
    ("กฎหมาย", r"กฎหมาย|นิติ|legal|lawyer|paralegal|compliance"),
    ("การศึกษา / ฝึกอบรม", r"ครู|อาจารย์|การศึกษา|education|teacher|tutor|trainer|ฝึกอบรม|training|ติวเตอร์"),
    ("ทรัพยากรบุคคล", r"ทรัพยากรบุคคล|\bhr\b|human resource|recruit|สรรหา|payroll|เงินเดือนและสวัสดิการ"),
    ("การตลาด / โฆษณา / ครีเอทีฟ", r"การตลาด|marketing|communication|โฆษณา|advertis|content|คอนเทนต์|graphic|"
        r"กราฟิก|ออกแบบ|designer|creative|ครีเอทีฟ|editor|บรรณาธิการ|\bpr\b|ประชาสัมพันธ์|social media|seo"),
    ("ขาย", r"งานขาย|\bsales?\b|ขาย|retail|consumer products|พนักงานขาย|เซลส์|business development|"
        r"account executive|ที่ปรึกษาการขาย"),
    ("บริการลูกค้า / Call Center", r"บริการลูกค้า|call cent|customer (service|support)|คอลเซ็นเตอร์|admin support|"
        r"ลูกค้าสัมพันธ์|customer relation"),
    ("วิศวกรรม", r"วิศวกร|engineer|วิศวกรรม|technician|ช่างเทคนิค|ช่างซ่อมบำรุง|maintenance|ซ่อมบำรุง"),
    ("ก่อสร้าง / สถาปัตย์ / อสังหา", r"ก่อสร้าง|สถาปัตย์|architect|construction|real estate|อสังหา|โฟร์แมน|foreman|"
        r"ออกแบบภายใน|interior|property|ช่างไฟ|ช่างปูน|ผู้รับเหมา|สำรวจ"),
    ("ขนส่ง / โลจิสติกส์ / คลังสินค้า", r"ขนส่ง|โลจิสติกส์|logistic|คลังสินค้า|warehouse|นำเข้า|ส่งออก|import|export|"
        r"พนักงานขับรถ|driver|shipping|ชิปปิ้ง|supply chain|ซัพพลายเชน|พัสดุ|forklift|โฟล์คลิฟท์"),
    ("ผลิต / โรงงาน / ควบคุมคุณภาพ", r"ผลิต|โรงงาน|manufactur|ควบคุมคุณภาพ|\bqc\b|production|operator|โอเปอเรเตอร์|"
        r"พนักงานประจำสายการผลิต|ฝ่ายผลิต|ประกอบ|ช่างเชื่อม|ช่างกลึง"),
    ("อาหาร / โรงแรม / ท่องเที่ยว / บริการ", r"อาหาร|เครื่องดื่ม|hospitality|tourism|โรงแรม|hotel|restaurant|ร้านอาหาร|"
        r"เชฟ|\bchef\b|barista|บาริสต้า|แม่บ้าน|พี่เลี้ยง|คนสวน|แคชเชียร์|cashier|พนักงานเสิร์ฟ|ท่องเที่ยว|"
        r"รปภ|รักษาความปลอดภัย|security guard|spa|สปา|ช่างตัดผม|เสริมสวย"),
    ("วิทยาศาสตร์ / เกษตร", r"วิทยาศาสตร์|science|เกษตร|ปศุสัตว์|ประมง|farming|agricult|นักวิจัย|research|เคมี|chemist|"
        r"ห้องปฏิบัติการ|laborator"),
    ("ธุรการ / จัดซื้อ / ประสานงาน", r"ธุรการ|จัดซื้อ|ประสานงาน|admin|secretary|เลขา|purchas|procure|coordinator|"
        r"office|ผู้ช่วย"),
]

OTHER = "อื่นๆ"
ALL = [name for name, _ in RULES] + [OTHER]
_COMPILED = [(name, re.compile(pat, re.I)) for name, pat in RULES]


def _match(text: str | None) -> str | None:
    if not text:
        return None
    for name, rx in _COMPILED:
        if rx.search(text):
            return name
    return None


def categorize(raw_category: str | None, title: str | None) -> str:
    return _match(raw_category) or _match(title) or OTHER
