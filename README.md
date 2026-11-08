# NexJ Notes

Bloco de notas seguro para Android, feito em Python (Kivy). Sem internet, sem anúncios, sem conta.

## Recursos
- Senha mestra + abertura por biometria (digital/rosto)
- Notas cifradas (AES) com chave derivada da senha (PBKDF2, 390 mil iterações)
- Lixeira com restauração; itens somem sozinhos após 30 dias
- **Destruição definitiva**: remove a nota, troca a chave de criptografia e sobrescreve o arquivo antigo, então cópias antigas ficam ilegíveis
- "Destruir cofre inteiro" (digite DESTRUIR)
- Bloqueia prints e miniatura nos apps recentes; tranca sozinho ao sair do app
- 5 senhas erradas = espera de 30 segundos

## Gerar o APK pelo GitHub (sem instalar nada no PC)
1. Crie um repositório no GitHub e envie estes arquivos (mantenha a pasta `.github`).
2. Abra a aba **Actions** → **Build APK** → **Run workflow**. O primeiro build leva 20 a 40 minutos.
3. Quando terminar, abra a execução e baixe `cofre-de-notas-apk` (arquivo .zip com o .apk dentro).
4. No celular, instale o .apk (permita "instalar de fontes desconhecidas").

## Testar no computador
```
pip install kivy cryptography
python main.py
```
(no PC a biometria não aparece; só a senha)

## Limites honestos
- Se você esquecer a senha, **não há recuperação**. É o ponto do cofre.
- Em memória flash de celular, nenhum apagamento é 100% garantido; por isso a destruição troca a chave, o que protege mesmo que sobre algum resíduo.
- A biometria guarda a chave num cofre do Android (Keystore) e só a libera depois da confirmação biométrica.
- Não há backup automático: trocar de celular ou desinstalar o app apaga as notas.
