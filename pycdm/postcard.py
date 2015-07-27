
import os
from pycdm import Collection, Object, File, PcdmReader

fedora4base = "http://localhost:8080/rest/"
reader = PcdmReader(context="../context.json")
base = reader.retrieve(fedora4base)

def create_postcards():
    c = Collection(slug='Postcards')
    c.setup()
    c.add_field('rdfs:label', "Postcards Collection")
    base.create_child(c)  # create it in F4

    pc = Object(slug='Postcard', ordered=True)
    pc.setup()
    pc.add_field('label', 'Postcard')
    base.create_child(pc)   # This is when we get created in F4   
    pcp = c.add_member(pc)  # And now we modify to add order :(

    front = Object(slug='Front')
    front.setup()
    base.create_child(front)
    pc.add_member(front)

    back = Object(slug='Back')
    back.setup()
    base.create_child(back)
    pc.add_member(back)

    # Now we need to update Postcard and Proxies to set order?

    ff = File(slug="front.jpg", filename="../front.jpg")
    ff.contentType = "image/jpeg"
    front.add_file(ff)

    bf = File(slug="back.jpg", filename="../back.jpg")
    bf.contentType = "image/jpeg"
    back.add_file(bf)

    return c

def retrieve_postcards():
	# c is Postcards Collection
	c = base.retrieve_child("Postcards", reader)
	c.build_contents(reader, recursive=True)   # Dangerous! 
	return c

def delete_postcards():
	slugs = ['Postcards', 'Postcard', 'Front', 'Back']
	for s in slugs:
		try:
			what = base.head_child(s, reader)
			what.delete(tombstone=True)  # Kill it dead
		except:
			pass

####
#
# WARNING: This will trash your repository, Samuel L Jackson like
# Hence the function name you don't want to type in front of your boss
#
####
def delete_every_mother_f_ing_thing():
	# head_children() is a generator so etags are updated
	# after each delete. 
	for kid in base.head_children(reader):
		kid.delete(tombstone=True)


