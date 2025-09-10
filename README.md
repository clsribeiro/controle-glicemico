# controle-glicemico
Página de relatório de controle glicêmico
# Controle Glicêmico - Relatórios

Este repositório armazena e exibe relatórios detalhados de controle glicêmico. O objetivo é fornecer uma visualização clara e acessível das tendências glicêmicas, contagem de carboidratos e doses de insulina sugeridas.

**Acesse a página de relatórios:** [https://clsribeiro.github.io/controle-glicemico/](https://clsribeiro.github.io/controle-glicemico/)

---

## Como Funciona

A solução utiliza uma abordagem de duas etapas:

1.  **Geração Local:** Um aplicativo web dinâmico (criado com Python e Flask) é executado localmente. Este aplicativo recebe um relatório de dados (`.mhtml`), o processa e gera uma página de relatório interativa.
2.  **Publicação Estática:** O arquivo HTML gerado é salvo através de um botão de download, movido para a pasta do projeto e então enviado para este repositório no GitHub. O recurso **GitHub Pages** é usado para hospedar publicamente esses relatórios estáticos.

## Como Publicar um Novo Relatório

O fluxo de trabalho para adicionar um novo relatório à página pública é o seguinte:

1.  **Execute o Analisador Local:** Certifique-se de ter as dependências instaladas (`pip install Flask beautifulsoup4`) e execute o script localmente:
    ```bash
    python analisador_glicemia_real.py
    ```

2.  **Gere e Baixe o Relatório:** Abra `http://120.0.0.1:5000` em seu navegador, carregue o arquivo `.mhtml` e, na página do relatório, clique no botão **"Salvar HTML"**.

3.  **Mova o Arquivo:** Encontre o relatório na sua pasta de "Downloads" e mova-o para a pasta `relatorios/` dentro deste projeto.

4.  **Atualize o Index:** Abra o arquivo `index.html` e adicione um novo item à lista (`<ul>`), criando um link para o arquivo recém-movido. Exemplo:
    ```html
    <li>
        <a href="relatorios/nome-do-novo-relatorio.html" target="_blank">
           Descrição do Novo Relatório (ex: Período de DD/MM a DD/MM)
        </a>
    </li>
    ```

5.  **Envie para o GitHub:** Use os comandos Git para enviar as atualizações:
    ```bash
    git add .
    git commit -m "Adiciona novo relatório de [período]"
    git push origin main
    ```

Após alguns instantes, o novo link aparecerá na página principal.