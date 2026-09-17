import ebooklib
from ebooklib import epub

def create_test_epub(filename="sample_book.epub"):
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier('test-id-12345')
    book.set_title('Sample Test Audiobook')
    book.set_language('en')
    book.add_author('Test Author')

    # Create chapters
    c1 = epub.EpubHtml(title='Chapter 1', file_name='chap_01.xhtml', lang='en')
    c1.content = '<h1>Chapter 1: The Initialization</h1><p>The morning sun broke across the horizon, casting long, sharp shadows over the quiet valley. In the small workshop, the machinery hummed with a low, steady cadence.</p>'

    c2 = epub.EpubHtml(title='Chapter 2', file_name='chap_02.xhtml', lang='en')
    c2.content = '<h1>Chapter 2: The Compilation</h1><p>As the files compiled one by one, a sense of anticipation filled the air. Systems that once required hours of manual intervention now executed in mere fractions of a second.</p>'

    c3 = epub.EpubHtml(title='Chapter 3', file_name='chap_03.xhtml', lang='en')
    c3.content = '<h1>Chapter 3: Execution Complete</h1><p>With a final confirmation chime, the build pipeline finished successfully. The output files were neatly organized and ready for deployment.</p>'

    # Add chapters to the book
    book.add_item(c1)
    book.add_item(c2)
    book.add_item(c3)

    # Define Table of Contents and Navigation
    book.toc = (epub.Link('chap_01.xhtml', 'Chapter 1', 'chap_1'),
                epub.Link('chap_02.xhtml', 'Chapter 2', 'chap_2'),
                epub.Link('chap_03.xhtml', 'Chapter 3', 'chap_3'))

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define spine (reading order)
    book.spine = ['nav', c1, c2, c3]

    # Write to file
    epub.write_epub(filename, book, {})
    print(f"Successfully generated: {filename}")

if __name__ == '__main__':
    create_test_epub()