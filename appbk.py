import requests, json, time, re, fitz
from io import BytesIO
from tqdm import tqdm
from dataclasses import dataclass

@dataclass
class Book:
    title: str
    size: str
    bundle: str

class API:
    def __init__(self, code):
        self.code = code
        self.base_url = "https://updatebook.elionline.com/catalogo/index.php/CatalogUsers"

    def _get_token(self):
        response = requests.get(f'{self.base_url}/LoginStudente/', params={'username': self.code})
        self.token = response.json()["token"]

    def _insegnamento_info(self):
        response = requests.get(f'{self.base_url}/ProfiloStudente/', params={'userToken': self.token}).json()
        self.materie, self.scuola = response["materie_insegnamento"], response["tipo_scuola"]

    def _get_bundle(self):
        response = requests.get(f'{self.base_url}/SchedeStudente/', params={'userToken': self.token, 'tipo_scuola': self.scuola, 'materie_insegnamento': self.materie}).json()[0]
        book = Book(response["titolo"], response["peso"], response["bundle"].split(".")[2])
        self.bundle = book.bundle
        self.server = response["server"].removesuffix("/")
        return book

    def _get_book_code(self):
        response = requests.get(f'{self.server}/0e7a5491c5e9c8e53df81a19b9061290/{self.bundle}/splash.xml', params={'d': int(time.time() * 1000)})
        self.book_code = re.findall(r"codice=\"(\d+)\"", response.text)[0]

    def generate_page_labels(self, data):
        page_labels = []
        current_chapter = ""
        current_chapter_start = 0
        for chapter, pages in data:
            current_chapter = chapter
            for page_url, page_label, page_index in pages:
                if page_label.isdigit():
                    if current_chapter != chapter:
                        page_labels.append({
                            'startpage': current_chapter_start,
                            'prefix': current_chapter,
                            'style': 'D',
                            'firstpagenum': 1
                        })
                        current_chapter = chapter
                        current_chapter_start = page_index
                else:
                    page_labels.append({
                        'startpage': page_index,
                        'prefix': page_label + '-',
                        'style': '',
                        'firstpagenum': 1
                    })

        # Add the last chapter
        page_labels.append({
            'startpage': current_chapter_start,
            'prefix': current_chapter,
            'style': 'D',
            'firstpagenum': 1
        })

        return page_labels

    def book_content(self):
        response = requests.get(f'{self.server}/0e7a5491c5e9c8e53df81a19b9061290/{self.bundle}/book_{self.book_code}/xml/progressive_data.json').json()
        capitoli, global_page_index = [], 0
        for capitolo in response["capitoli"]:
            nome = capitolo["nome"]
            pagine = [(f'{self.server}/0e7a5491c5e9c8e53df81a19b9061290/{self.bundle}{p["risorse"][0][0].replace("swf", "png")}', p["nome"], i + global_page_index) for i, p in enumerate(capitolo["pagine"]) if p["risorse"][0][0].endswith("swf")]
            capitoli.append((nome, pagine))
            global_page_index += len(pagine)
        return capitoli


if __name__ == "__main__":
    code = input("Inserisci il codice del libro: ")
    api = API(code)
    api._get_token()
    api._insegnamento_info()
    book_infos = api._get_bundle()
    print(f'''
[+] Book Found:
    - title: {book_infos.title}
    - size: {book_infos.size}
''')
    api._get_book_code()
    book = api.book_content()
    page_labels = api.generate_page_labels(book)
    chapters = [(1, chapter[0], chapter[1][0][2]) for chapter in book]

    doc = fitz.open()
    for idx, chapter in enumerate(book):
        chapter_title, pages = chapter
        for page_info in tqdm(pages, desc=f"[{idx}] Downloading unit: {chapter_title}", ascii="░▒█"):
            url, label, index = page_info
            response = requests.get(url)
            if response.status_code == 200:
                img = fitz.open("png", response.content)
                pdfbytes = img.convert_to_pdf()
                imgpdf = fitz.open("pdf", pdfbytes)
                doc.insert_pdf(imgpdf)

    doc.set_toc(chapters)
    doc.set_page_labels(page_labels)
    doc.save(f"{book_infos.title}.pdf")

