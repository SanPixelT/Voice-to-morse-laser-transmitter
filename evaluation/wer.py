# Step 4: score the transcripts. 40 clips (LJ001-0001 to 0022 and 0052 to 0069) were run
# through laptop_test.py with and without noise reduction; the outputs are pasted in below.
# Accuracy = 1 - WER.

import re
import jiwer

reference = (
    "In the only sense with which we are at present concerned differs from most "
    "if not from all the arts and crafts represented in the exhibition "
    "In being comparatively modern "
    "Although the Chinese took impressions from wood blocks engraved in relief for centuries before the woodcutters of the Netherlands by a similar process "
    "Produced the block books which were the immediate predecessors of the true printed book "
    "Invention of movable metal letters in the middle of the fifteenth century may justly be considered as the invention of the art of printing "
    "And it is worth mention in passing that as an example of fine typography "
    "The earliest book printed with movable types, the Gutenberg, or 'forty-two-line Bible' of about 1455 "
    "Has never been surpassed "
    "Then for our purpose may be considered as the art of making books by means of movable types "
    "Now as all books not primarily intended as picture-books consist principally of types composed to form letterpress "
    "It is of the first importance that the letter used should be fine in form "
    "Especially as no more time is occupied or cost incurred in casting, setting or printing beautiful letters "
    "In the same operations with ugly ones "
    "And it was a matter of course that in the Middle Ages when the craftsmen took care that beautiful form should always be a part of their productions whatever they were "
    "The forms of printed letters should be beautiful and that their arrangement on the page should be reasonable and a help to the shapeliness of the letters themselves "
    "The Middle Ages brought calligraphy to perfection and it was natural therefore "
    "That the forms of printed letters should follow more or less closely those of the written character and they followed them very closely "
    "The first books were printed in black letter i.e. the letter which was a Gothic development of the ancient Roman character "
    "And which developed more completely and satisfactorily on the side of the 'lower-case' than the capital letters "
    "The 'lower-case' being in fact invented in the early Middle Ages "
    "The earliest book printed with movable type the aforesaid Gutenberg Bible is printed in letters which are an exact imitation "
    "Of the more formal ecclesiastical writing which obtained at that time; this has since been called 'missal type' "
    "Yet their type is artistically on a much lower level than Jenson's and in fact "
    "They must be considered to have ended the age of fine printing in Italy "
    "Jenson however had many contemporaries who used beautiful type "
    "some of which – as e.g. that of Jacobus Rubeus or Jacques le Rouge -- is scarcely distinguishable from his "
    "It was these great Venetian printers together with their brethren of Rome Milan "
    "Parma and one or two other cities who produced the splendid editions of the Classics which are one of the great glories of the printer's art "
    "And are worthy representatives of the eager enthusiasm for the revived learning of that epoch. By far "
    "the greater part of these Italian printers it should be mentioned were Germans or Frenchmen working under the influence of Italian opinion and aims "
    "It must be understood that through the whole of the fifteenth and the first quarter of the sixteenth centuries "
    "The Roman letter was used side by side with the Gothic "
    "Even in Italy most of the theological and law books were printed in Gothic letter "
    "Which was generally more formally Gothic than the printing of the German workmen "
    "Many of whose types indeed like that of the Subiaco works are of a transitional character "
    "This was notably the case with the early works printed at Ulm and in a somewhat lesser degree at Augsburg "
    "In fact Gunther Zeiner's first type (afterwards used by Schussler) is remarkably like the type of the before-mentioned Subiaco books "
    "In the Low Countries and Cologne which were very fertile of printed books Gothic was the favourite "
    "The characteristic Dutch type as represented by the excellent printer Gerard Leew is very pronounced and uncompromising Gothic "
    "This type was introduced into England by Wynkyn de Worde Caxton's successor"
)


hypothesis_with_noise_reduction = (
    "In the only sense with which we are at present concerned differs from most if not from all the arts and crafts represented in the exhibition "
    "The comparatively modern "
    "The Chinese had took impressions of woodwork in grave finally sent before the wood cutters of the Netherlands by a similar process "
    "Produce block books which were the immediate predecessors of the fruit printed book "
    "Invention of movable metal letters in the middle of the fifth century may justly be considered as the invention of the art centre "
    "It is worth mention in passing that as an example of fine typography "
    "The earliest type in Gothenburg for forty-two-line bible of about fourteen fifty-five "
    "Never been to pass "
    "Then for our purpose may be considered as the art of making books by means of movable types "
    "Now as all books not primarily intended as picture books consist principally of types composed before letter press "
    "It is the first importance that the letter used should be fine in form "
    "Especially as no more time is occupied or cost in curry in casting setting or printing beautiful letters "
    "In the same operations with "
    "ugly ones "
    "And it was a matter of course that in the Middle Ages when the craftsmen took care that beautiful form should always be a part of their productions whatever they were "
    "Forms of printed letter should be beautiful and that the arrangement on the page reasonable and a help to the shapeliness of the letters themselves "
    "Middle Ages brought calligraphy to perfection and it was natural therefore "
    "The forms of printed letters to follow more or less closely those of the written character and they followed them very closely "
    "first books were printed in black letter I letter which was a gothic development of the ancient roman character "
    "And which developed more completely and satisfactorily on the side of the lower case then the capital letters "
    "The lower case being in fact invented in the early Middle Ages "
    "The earliest book printed with movable type said Gutenberg bible is printed in letters which are in exact imitation "
    "Of the more formal ecclesiastical writing which obtained at that time this has since been called missile cut "
    "They're types artistically on a much lower level than jenson's and in fact "
    "Must be considered to have ended the age of fine printing in Italy "
    "However had many contemporaries who used beautiful type "
    "Some of which as that of the covetous or Jacques scarcely distinguishable from his "
    "Was these great venetian printers together with their brethren of Rome belong "
    "And one or two other cities produce the foundations of the classes we are one of the great glories of the printer's art "
    "Are worthy representatives of the eager enthusiasm for the revived learning of that epoch by far "
    "Greater part of these Italian printers it should be mentioned or Germans or Frenchmen working under the influence of Italian opinion and aims "
    "Must be understood that to the whole of the fifty the first quarter of the sixteenth centuries "
    "A letter was used side by side with the gate "
    "Even in Italy most of the theological and law books were printed in gothic letter "
    "Was generally more formally open that the printing of the German workmen "
    "Many of whose types indeed like that of the subiaco works are oriental character "
    "This was notably the case with the early works printed at all and in a somewhat lesser degree at all the "
    "In fact on the signers first type afterwards used by sheer is remarkably like the type of the before mentioned Subiaco "
    "The low countries and alone were very fertile  of printed books Garrick was the favourite "
    "characteristic Dutch type as represented by the excellent printer the arroyo is very pronounced and uncompromising Gothic "
    "Type was introduced into England I went work a successor"
)


hypothesis_without_noise_reduction = (
    "In the only sense with which we are at present concerned differs from most if not from all the arts and crafts represented in the exhibition "
    "In comparatively modern "
    "Although the Chinese to impressions from woodblocks in grave interfere before the wood cutters of the Netherlands by a similar places "
    "Produced the block books before immediate predecessors of the preferred book "
    "Invention of movable metal letters in the middle of the fifteenth century may justly be considered as the invention of the attainted "
    "It is worth mention in passing that as an example of fine typography "
    "All the book ended with movable types elucidator forty two line bible of about fourteen fifty five "
    "Never in the past "
    "Then for our purpose may be considered as the heart of making books by means of movable types "
    "Now as all books not primarily intended as picture books consist principally of pipes composed for letter press "
    "It is the first importance that the letter used should be fine in form "
    "Especially as no more time is occupied continued casting setting for printing beautiful letters "
    "In the same operations with ugly ones "
    "And it was a matter of course that in the Middle Ages when the craftsmen took care that beautiful form should always be a part of their productions whatever they were "
    "For as a printed letters should be beautiful and that the arrangement on the page in reasonable and a help to the shapeliness of the letters themselves "
    "It ages brought calligraphy to perfection and it was natural therefore "
    "A form of printed letters to follow more or less closely those of the written character they followed them very closely "
    "First books were printed in black letter the letter which was a gothic development of the ancient roman character "
    "And which developed more completely and satisfactorily on the side of the lower case then the capital levers "
    "The lower case being in fact invented in the early Middle Ages "
    "The earliest book printed with movable type said gluttonie is printed in letters exact imitation "
    "The more formal ecclesiastical writing at that time this has since been called missile to "
    "They're tied tsaristic ally on a much lower level than jenson's and in fact "
    "Must be considered to have ended the age of fine printing in Italy "
    "However had many contemporaries who used beautiful pipe "
    "Some of which as that of the cobwebs for jacques scarcely distinguishable from his "
    "As these great venetian printers together with their brethren of rome belong "
    "And one or two other cities produce the editions of the classics which are one of the great glories of the printer's art "
    "The representatives of the eager enthusiasm he revived learning of that epoch by far "
    "At parts of these Italian printers it should be mentioned or Germans or Frenchmen working under the influence of Italian opinion and aims "
    "Must be understood that to the whole of the fifteen the first quarter of the sixteenth centuries "
    "A letter was used side by side with the gate "
    "Even in Italy most of the theological and laws were printed in gothic letter "
    "Was generally more formally gothic that the printing of the German worked him "
    "Many of those types indeed like that of the subiaco works the rendition character "
    "This was notably the case would be early works printed at all and in a somewhat lesser degree at all mister "
    "In fact on the signers first type afterwards used by colour is remarkably like the type of the before mentioned suitable "
    "The low countries and alone we're very careful of printed books gothic was the favourite "
    "Characteristic Dutch type as represented by the excellent printer charogne is very pronounced and uncompromising got "
    "Type was introduced into England I went word a successor"
)



# Raw text, as in the report: capital letters and punctuation count as errors
wer_with_noise_reduction = jiwer.wer(reference, hypothesis_with_noise_reduction)
wer_without_noise_reduction = jiwer.wer(reference, hypothesis_without_noise_reduction)

print(f"Word Error Rate with Noise Reduction: {wer_with_noise_reduction:.3f}")
print(f"Word Error Rate without Noise Reduction: {wer_without_noise_reduction:.3f}")

print(f"Accuracy with Noise Reduction: {1-wer_with_noise_reduction:.3f}")
print(f"Accuracy without Noise Reduction: {1-wer_without_noise_reduction:.3f}")


# Added in 2026: the same comparison after lowercasing and removing punctuation, which is the
# usual way to compute WER (DeepSpeech only outputs lowercase letters, so "Gothic" vs "gothic"
# shouldn't count as a mistake).
def normalise(text):
    text = text.lower().replace("-", " ").replace("'", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return " ".join(text.split())

wer_nr_norm = jiwer.wer(normalise(reference), normalise(hypothesis_with_noise_reduction))
wer_no_nr_norm = jiwer.wer(normalise(reference), normalise(hypothesis_without_noise_reduction))

print()
print(f"Normalised WER with Noise Reduction: {wer_nr_norm:.3f}")
print(f"Normalised WER without Noise Reduction: {wer_no_nr_norm:.3f}")
print(f"Normalised accuracy with Noise Reduction: {1-wer_nr_norm:.3f}")
print(f"Normalised accuracy without Noise Reduction: {1-wer_no_nr_norm:.3f}")
