FROM public.ecr.aws/lambda/python:3.11

# Install poppler-utils for pdf2image (PDF → PNG conversion).
# Amazon Linux 2023 uses dnf; poppler-utils provides pdftoppm and pdfinfo.
RUN dnf install -y poppler-utils && dnf clean all

# Install Python dependencies before copying application code so Docker can
# cache this layer when only handler.py changes.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy function code last to maximise layer caching.
COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
