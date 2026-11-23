# Makefile do projecto ddt (RC-I 2026-2027, ISPTEC)
#
# O projecto esta escrito em Python 3, que nao precisa de compilacao.
# Esta Makefile serve para: verificar a sintaxe, arrancar o servidor de
# arranque, arrancar um no ddt e gerir as maquinas virtuais Vagrant.
#
# Os alvos "boot", "run" e "check" correm DENTRO das VMs (Linux).
# Os alvos "up", "halt" e "status" correm no computador anfitriao.
#
# Valores por omissao (podem ser mudados na linha de comandos):
#   make run PORT=5002
#   make run PORT=5002 BOOT_IP=127.0.0.1 BOOT_PORT=58000

PYTHON    ?= python3
PORT      ?= 5000
BOOT_IP   ?= 192.168.56.21
BOOT_PORT ?= 58000
FILES     := ddt.py bootserver.py

.PHONY: all help check boot run clean up halt status

all: check

help:
	@echo "Alvos disponiveis:"
	@echo "  make check    verifica a sintaxe de ddt.py e bootserver.py"
	@echo "  make boot     arranca o servidor de arranque UDP (porta $(BOOT_PORT))"
	@echo "  make run      arranca um no ddt (PORT=$(PORT), arranque $(BOOT_IP):$(BOOT_PORT))"
	@echo "  make clean    apaga ficheiros temporarios do Python"
	@echo "  make up       liga as VMs boot e no1 (no anfitriao)"
	@echo "  make halt     desliga todas as VMs (no anfitriao)"
	@echo "  make status   mostra o estado das VMs (no anfitriao)"

check:
	@$(PYTHON) -c "import ast, sys; [ast.parse(open(f, encoding='utf-8').read(), f) for f in sys.argv[1:]]; print('Sintaxe OK')" $(FILES)

boot:
	$(PYTHON) bootserver.py -p $(BOOT_PORT)

run:
	$(PYTHON) ddt.py -t $(PORT) -i $(BOOT_IP) -p $(BOOT_PORT)

clean:
	rm -rf __pycache__ *.pyc

up:
	vagrant up boot no1

halt:
	vagrant halt

status:
	vagrant status
