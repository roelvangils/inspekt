class Inspekt < Formula
  include Language::Python::Virtualenv

  desc "Browser inspection, accessibility testing, and automation CLI"
  homepage "https://github.com/roelvangils/inspekt"
  url "https://github.com/roelvangils/inspekt/archive/refs/tags/v0.5.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"  # Update after creating the release
  license "MIT"
  head "https://github.com/roelvangils/inspekt.git", branch: "main"

  depends_on "python@3.12"

  # Pillow build dependencies
  depends_on "jpeg"
  depends_on "libpng"
  depends_on "libtiff"
  depends_on "webp"
  depends_on "zlib"

  # ============================================================================
  # Python Dependencies
  # ============================================================================
  # To regenerate these resource blocks, run:
  #
  #   pip install homebrew-pypi-poet
  #   poet inspekt > resources.txt
  #
  # Then paste the resource blocks here.
  #
  # NOTE: The Click dependency currently uses git main branch due to a regression
  # in 8.1.x. Once Click 8.2.0+ is released, update pyproject.toml to use the
  # stable version before generating resources.
  # ============================================================================

  # Core dependencies (alphabetical order)
  # These are placeholder entries - regenerate with poet after Click is released

  resource "aiofiles" do
    url "https://files.pythonhosted.org/packages/0b/03/a88171e277e8caa88a4c77808c20ebb04ba74cc4681bf1e9416c862de237/aiofiles-24.1.0.tar.gz"
    sha256 "22a075c9e5a3810f0c2e48f3f546c153f94b6f6e5a5a86a2be5eb974c6d6877e"
  end

  resource "aiohttp" do
    url "https://files.pythonhosted.org/packages/17/7e/16e57e6cf20eb62481a2f9ce8674328407187950ccc602ad07c685279141/aiohttp-3.10.10.tar.gz"
    sha256 "0631dd7c9f0822cc61c88586ca76d5b5ada26538571f04e91f6f050a0309c77c"
  end

  resource "beautifulsoup4" do
    url "https://files.pythonhosted.org/packages/b3/ca/824b1195773571e185c5a50e71a4fc6c7815e6a228e239e7e8da8d75c369/beautifulsoup4-4.12.3.tar.gz"
    sha256 "74e3d1928edc070d21748185c46e3fb33490f22f52a3addee9aee0f4f7781051"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/96/d3/f04c7bfcf5c1862a2a5b845c6b2b360488cf47af55dfa79c98f6a6bf98b5/click-8.1.7.tar.gz"
    sha256 "ca9853ad459e787e2192211578cc907e7594e294c7ccc834310722b41b9ca6de"
  end

  resource "coloraide" do
    url "https://files.pythonhosted.org/packages/eb/43/d4e5e6f34791990d74c89e822f4b4fd1297df9a6b9ec5d79d42db28fc250/coloraide-3.3.1.tar.gz"
    sha256 "f6e8fc6e8fc0b24e28352eb54fba4f51de6b6e11f48c44ed09d1f0c1e8bfa7e4"
  end

  resource "fastapi" do
    url "https://files.pythonhosted.org/packages/93/72/d83b98a8ffd4f59f0894e6038e7b61ff7b4e5e7b8c5c6c8e0a7f4e8a3e0a/fastapi-0.115.0.tar.gz"
    sha256 "220f3e15df3e9797123eb66e6d7c4f6f14d7c23e7f2dbdc2e6bf4a14f9b4f0a4"
  end

  resource "jinja2" do
    url "https://files.pythonhosted.org/packages/ed/55/39036716d19cab0747a5020fc7e907f362fbf48c984b14e62127f7e68e5d/jinja2-3.1.4.tar.gz"
    sha256 "4a3aee7acbbe7303aede8e9648d13b8bf88a429282aa6122a993f0ac800cb369"
  end

  resource "markdown" do
    url "https://files.pythonhosted.org/packages/54/28/3af612670f82f4c056911fbbbb42760255801b3068c48de792d354ff4472/markdown-3.7.tar.gz"
    sha256 "2ae2471477cfd02dbbf038d5d9bc226d40def84b4fe2986e49b59b6b472bbed2"
  end

  resource "markdownify" do
    url "https://files.pythonhosted.org/packages/12/45/40f5e1c88372b9702db7a5f6ab6bb0acf1b7e8c7b5b7e3c1b8e8c0e5a6c9/markdownify-0.13.1.tar.gz"
    sha256 "0f5e5c8e3f8f3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b3b"
  end

  resource "mcp" do
    url "https://files.pythonhosted.org/packages/00/00/mcp-1.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "packaging" do
    url "https://files.pythonhosted.org/packages/51/65/50db4dda066951078f0a96cf12f4b9ada6e4b811516bf0262c0f4f7064d4/packaging-24.1.tar.gz"
    sha256 "026ed72c8ed3fcce5bf8950572258698927fd1dbda10a5e981cdf0ac37f4f002"
  end

  resource "pillow" do
    url "https://files.pythonhosted.org/packages/a5/26/0d95c04c868f6bdb0c447e3ee2de5564411845e36a858cfd63766bc7b563/pillow-10.4.0.tar.gz"
    sha256 "166c1cd4d24309b30d61f79f4a9114b7b2313d7450912277855ff5dfd7cd4a06"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/df/e4/ba44652d562cbf0540c7d61e7e8a9e2c8d5e2c4d2e2e3f5a6b7c8d9e0f1a/pydantic-2.9.2.tar.gz"
    sha256 "d155cef71265d1e9807ed1c32b4c8deec042a44a50a4188b25ac67e0a5e4c7d4"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/54/ed/79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/pyyaml-6.0.2.tar.gz"
    sha256 "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
  end

  resource "requests" do
    url "https://files.pythonhosted.org/packages/63/70/2bf7780ad2d390a8d301ad0b550f1581eadbd9a20f896afe06353c2a2913/requests-2.32.3.tar.gz"
    sha256 "55365417734eb18255590a9ff9eb97e9e1da868d4ccd6402399eaf68af20a760"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/aa/9e/1784d15b057b0075e5136445aaea92d23955aad2c93eaede673718a40d95/rich-13.9.2.tar.gz"
    sha256 "51a2c62057461aaf7f2b58afbd6b1e2acca89b1a5b1f9e9e9d9c5f4e8b9a7c6d"
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/e0/fc/1d785078eefd6945f3e5bab5c076e4230698046231eb0f3747bc5c8fa992/uvicorn-0.31.0.tar.gz"
    sha256 "13bc21373d103859f68fe739608e2eb054a816dea79189bc3ca08ea89a275906"
  end

  resource "websockets" do
    url "https://files.pythonhosted.org/packages/2e/62/7a7874b7285413c954a4cca3c11fd851f11b2fe5b4ae2d9bee4f6d9bdb10/websockets-13.1.tar.gz"
    sha256 "a3b3366087c1bc0a2795111edcadddb8b3b59509d5db5d7ea3fdd69f954a8878"
  end

  # Add transitive dependencies as needed (these will be auto-detected by poet)
  # Common ones include: certifi, charset-normalizer, idna, urllib3, soupsieve,
  # typing-extensions, annotated-types, pydantic-core, starlette, etc.

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      To complete Inspekt setup:

      1. Start the bridge server:
           inspekt start --daemon

      2. Install the browser extension:
           https://inspekt.dev/docs/getting-started/installation

      3. Verify the installation:
           inspekt --version
           inspekt status

      For shell completions, run:
           inspekt completions install

      Documentation: https://inspekt.dev
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/inspekt --version")
    assert_match "Usage:", shell_output("#{bin}/inspekt --help")
  end
end
