--
-- PostgreSQL database dump
--


-- Dumped from database version 18.3 (Debian 18.3-1.pgdg13+1)
-- Dumped by pg_dump version 18.2

-- Started on 2026-06-15 18:09:36

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 221 (class 1259 OID 16420)
-- Name: counter; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.counter (
    id integer NOT NULL,
    val integer DEFAULT 1,
    CONSTRAINT counter_one_row CHECK ((id = 1))
);



--
-- TOC entry 225 (class 1259 OID 16447)
-- Name: customers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customers (
    id integer NOT NULL,
    phone text NOT NULL,
    name text NOT NULL,
    email text,
    address text,
    city text,
    total_orders integer DEFAULT 0,
    total_spent numeric(12,2) DEFAULT 0,
    last_order_date text,
    created text DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'::text),
    updated text DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'::text)
);



--
-- TOC entry 224 (class 1259 OID 16446)
-- Name: customers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.customers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- TOC entry 3493 (class 0 OID 0)
-- Dependencies: 224
-- Name: customers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.customers_id_seq OWNED BY public.customers.id;


--
-- TOC entry 219 (class 1259 OID 16389)
-- Name: orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orders (
    id text NOT NULL,
    name text NOT NULL,
    phone text NOT NULL,
    type text NOT NULL,
    model text,
    qty integer DEFAULT 0,
    price numeric(12,2) DEFAULT 0,
    amount numeric(12,2) DEFAULT 0,
    advance numeric(12,2) DEFAULT 0,
    payment text,
    delivery text,
    priority text DEFAULT 'Normal'::text,
    handler text,
    req text,
    matter text,
    commitments text,
    status text DEFAULT 'New'::text,
    created text DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'::text),
    customer_id integer
);



--
-- TOC entry 220 (class 1259 OID 16407)
-- Name: stock; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stock (
    num text NOT NULL,
    arrived integer DEFAULT 0,
    current integer DEFAULT 0,
    dealer numeric(12,2) DEFAULT 0,
    sell numeric(12,2) DEFAULT 0,
    nop numeric(12,2) DEFAULT 0,
    vendor text
);



--
-- TOC entry 223 (class 1259 OID 16429)
-- Name: stock_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stock_history (
    id integer NOT NULL,
    num text NOT NULL,
    action text NOT NULL,
    old_qty integer,
    new_qty integer,
    qty_change integer,
    notes text,
    created text DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'::text)
);



--
-- TOC entry 222 (class 1259 OID 16428)
-- Name: stock_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.stock_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;



--
-- TOC entry 3494 (class 0 OID 0)
-- Dependencies: 222
-- Name: stock_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--



--
-- TOC entry 3321 (class 2604 OID 16450)
-- Name: customers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers ALTER COLUMN id SET DEFAULT nextval('public.customers_id_seq'::regclass);


--
-- TOC entry 3319 (class 2604 OID 16432)
-- Name: stock_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock_history ALTER COLUMN id SET DEFAULT nextval('public.stock_history_id_seq'::regclass);


--
-- TOC entry 3332 (class 2606 OID 16427)
-- Name: counter counter_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.counter
    ADD CONSTRAINT counter_pkey PRIMARY KEY (id);


--
-- TOC entry 3336 (class 2606 OID 16463)
-- Name: customers customers_phone_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_phone_key UNIQUE (phone);


--
-- TOC entry 3338 (class 2606 OID 16461)
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- TOC entry 3328 (class 2606 OID 16406)
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- TOC entry 3334 (class 2606 OID 16440)
-- Name: stock_history stock_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock_history
    ADD CONSTRAINT stock_history_pkey PRIMARY KEY (id);


--
-- TOC entry 3330 (class 2606 OID 16419)
-- Name: stock stock_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock
    ADD CONSTRAINT stock_pkey PRIMARY KEY (num);


--
-- TOC entry 3339 (class 2606 OID 16464)
-- Name: orders orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE SET NULL;


--
-- TOC entry 3340 (class 2606 OID 16441)
-- Name: stock_history stock_history_num_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock_history
    ADD CONSTRAINT stock_history_num_fkey FOREIGN KEY (num) REFERENCES public.stock(num);


-- Completed on 2026-06-15 18:10:01

--
-- PostgreSQL database dump complete
--


