# Per the Apify Python actor template (apify/actor-templates, python-beautifulsoup), pinned to 3.11 like the rest of Trophy.
FROM apify/actor-python:3.11

COPY --chown=myuser:myuser requirements.txt ./
RUN echo "Python version:" \
 && python --version \
 && echo "Pip version:" \
 && pip --version \
 && echo "Installing dependencies:" \
 && pip install -r requirements.txt \
 && echo "All installed Python packages:" \
 && pip freeze

COPY --chown=myuser:myuser . ./
RUN python -m compileall -q src/rulebook_scraper/

CMD ["python", "-m", "rulebook_scraper"]
ENV PYTHONPATH=/usr/src/app/src
