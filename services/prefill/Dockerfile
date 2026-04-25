FROM public.ecr.aws/lambda/python:3.11

# Poppler provides pdftoppm/pdfinfo for the image fallback path.
RUN yum install -y poppler-utils && yum clean all

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
