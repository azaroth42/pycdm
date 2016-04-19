
from ldp import DirectContainer
from pycdm import Collection as PcdmCollection
from pycdm import Object as PcdmObject
from pycdm import PcdmReader as PcdmReaderBase

class PcdmReader(PcdmReaderBase):
	def __init__(self, context = None):
		super(PcdmReader, self).__init__(context)
		self.class_map['pcdm:Object'] = Object
		self.class_map['pcdm:Collection'] = Collection
		self.property_map['pcdm:hasMaster'] = 'master'
		self.property_map['pcdm:hasFileSet'] = 'filesets'

class Collection(PcdmCollection):
	filesets = []
	filesetsContainer = None

	def __init__(self, uri="", slug="", ordered=False):
		super(Collection, self).__init__(uri=uri, slug=slug, ordered=ordered)
		self.filesets = []
		self.filesetsContainer = None

	def build_from_rdf(self, reader):
		super(Collection, self).build_from_rdf(reader)
		filesetsuri = os.path.join(self.uri, 'filesets')
		self.filesetsContainer = reader.retrieve(filesetsuri)

	def setup(self):
		super(Collection, self).setup()
		fs = DirectContainer(slug='filesets')
		fs.membershipResource = self
		fs.hasMemberRelation = 'pcdm:hasFileSet'
		self.filesetsContainer = fs

	def build_contents(self, reader, recursive=False):
		super(Collection, self).build_contents(reader, recursive)
		self.filesetsContainer.build_contents(reader, recursive)
		if recursive:
			for fs in self.filesets:
				fs.build_contents(reader, recursive)

	def create(self):
		super(Collection, self).create()
		self.create_child(self.filesetsContainer)
		self.update_etag()

	def add_fileset(self, fileset):
		self.filesetsContainer.create_child(fileset)

class Object(PcdmObject):
	filesets = []
	filesetsContainer = None

	def __init__(self, uri="", slug="", ordered=False):
		super(Object, self).__init__(uri=uri, slug=slug, ordered=ordered)
		self.filesets = []
		self.filesetsContainer = None

	def build_from_rdf(self, reader):
		super(Object, self).build_from_rdf(reader)
		filesetsuri = os.path.join(self.uri, 'filesets')
		self.filesetsContainer = reader.retrieve(filesetsuri)

	def setup(self):
		super(Object, self).setup()
		fs = DirectContainer(slug='filesets')
		fs.membershipResource = self
		fs.hasMemberRelation = 'pcdm:hasFileSet'
		self.filesetsContainer = fs

	def build_contents(self, reader, recursive=False):
		super(Object, self).build_contents(reader, recursive)
		self.filesetsContainer.build_contents(reader, recursive)
		if recursive:
			for fs in self.filesets:
				fs.build_contents(reader, recursive)

	def create(self):
		super(Object, self).create()
		self.create_child(self.filesetsContainer)
		self.update_etag()

	def add_fileset(self, fileset):
		self.filesetsContainer.create_child(fileset)

class FileSet(PcdmObject):
	master = []
	masterContainer = None

	def __init__(self, uri="", slug="", ordered=False):
		super(FileSet, self).__init__(uri=uri, slug=slug, ordered=ordered)
		self.master = []
		self.masterContainer = None

	def build_from_rdf(self, reader):
		super(FileSet, self).build_from_rdf(reader)
		masteruri = os.path.join(self.uri, 'master')
		self.masterContainer = reader.retrieve(masteruri)

	def setup(self):
		super(FileSet, self).setup()
		m = DirectContainer(slug='master')
		# this is '' before self is created ...
		m.membershipResource = self
		m.hasMemberRelation = 'pcdm:hasMaster'
		self.masterContainer = m

	def build_contents(self, reader, recursive=False):
		super(FileSet, self).build_contents(reader, recursive)
		self.masterContainer.build_contents(reader, recursive)

	def create(self):
		super(FileSet, self).create()
		self.create_child(self.masterContainer)
		self.update_etag()

	def add_master_file(self, what):
		self.masterContainer.create_child(what)



